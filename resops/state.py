"""
The readiness ladder — one state per workload, the irrefutable verdict.

A workload sits on exactly ONE rung. You climb by clearing ResOps stages, each
gated by evidence; you stop at the first stage that doesn't clear, and that rung
IS your state. The stage you're stuck on is the next thing to fix.

    UNDISCOVERED ─Discover─▸ DISCOVERED ─Protect─▸ PROTECTED
        ─Detect─▸ MONITORED ─Recover─▸ RECOVERABLE ─Scan─▸ TRUSTED
        ─Validate─▸ VALIDATED

Scan sits between Recover and Validate on purpose: Recover asks whether there IS
a recent recovery point, Scan asks whether that point carries a known threat, and
Validate asks whether a real restore proved it. You cannot honestly validate a
recovery from a point you never checked.

State = capability (what's TRUE now). It never carries a parallel "FAIL" track:
a read error doesn't invent a failure state, it just leaves you on the rung below
with the HTTP reason — so the only states are the six rungs. Policy lives
elsewhere (the gate decides PROMOTE/HOLD; Improve reads the trend).

`classify()` is PURE — it takes already-fetched reads and returns a Ladder. No
network, no clock. That's what makes the truth table trivially testable. The one
I/O boundary is `gather()`: it does the reads (read-only GETs) and hands a Reads
to classify(). Keep network out of everything else.
"""
from __future__ import annotations

import enum
import json
from dataclasses import dataclass, field
from pathlib import Path

from .client import Client
from .reads import (
    SUMMARY_CLIP, _find_vm, _get, _plan_name, _recovery_proof, _vms_in_group,
    threat_attestation, find_vmgroup_id, vmgroup_name,
)


@enum.unique
class State(enum.Enum):
    """The rungs, in order. `rank` gives a total ordering for trend + the gate."""
    UNDISCOVERED = 0
    DISCOVERED = 1
    PROTECTED = 2
    MONITORED = 3
    RECOVERABLE = 4
    TRUSTED = 5
    VALIDATED = 6

    @property
    def rank(self) -> int:
        return self.value

    def __lt__(self, other: "State") -> bool:
        return self.rank < other.rank

    def __str__(self) -> str:
        return self.name


# The ResOps stages, in climb order. Each is the TRANSITION that lifts a workload
# from one rung to the next; the label names "the next thing to do". (The
# cloud-native lens per stage lives in evidence.DEVOPS_LENS, keyed by the
# lower-cased stage name, and is rendered in --detail.)
STAGES = ("Discover", "Protect", "Detect", "Recover", "Scan", "Validate")

ROOT = Path(__file__).resolve().parent.parent   # repo root — resolves relative
                                                # attestation_file paths in config


@dataclass(frozen=True)
class Reads:
    """The raw reads classify() folds into a state. Built by the runner (P2);
    hand-built in tests. Keeping it a plain bag of already-fetched values is what
    lets classify() stay pure — no client, no clock."""
    vm_name: str
    vmgroup: dict = field(default_factory=dict)   # GET V4/VMGroup/{id}
    vmgroup_error: str = ""
    vm: dict | None = None                        # the matched record from GET /VM
    vm_error: str = ""
    # Who attests this recovery point is trustworthy, and what they found.
    # None means NOBODY has — which is a gap, never a pass. {"source", "clean", ...}
    attestation: dict | None = None
    attestation_error: str = ""
    proof: dict | None = None                     # the drill's OWN restore job, confirmed
    proof_error: str = ""


@dataclass(frozen=True)
class Rung:
    """One stage's outcome — the per-stage detail row (replaces FunctionResult
    in the --detail view)."""
    stage: str
    state_after: State        # the rung this stage lifts you onto when it clears
    passed: bool | None       # True cleared · False blocked here · None not reached
    summary: str
    evidence: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Ladder:
    """A workload's position on the ladder — the whole verdict of one run."""
    state: State
    blocked_stage: str | None     # the ResOps stage that didn't clear (None at VALIDATED)
    reason: str                   # one human line: why blocked, or the proof line
    blocked_by_error: bool        # True if a read error blocked us (not a real gap)
    rungs: list                   # list[Rung] — every stage, for the detail view

    @property
    def promotable(self) -> bool:
        """Capability-only — the gate adds the freshness policy on top."""
        return self.state is State.VALIDATED


def gather(client: Client, workload: dict) -> Reads:
    """The I/O boundary: read-only GETs → a Reads for classify(). Never raises —
    a failed read becomes an error string on Reads, which classify() turns into a
    block on the matching rung (never a crash, never a state above it).

    Reads all three lanes regardless of where the climb will stop, so the evidence
    bundle is always complete even when the workload blocks on an early rung."""
    vm_name = workload.get("vm_name", "")
    group_id = workload.get("vm_group_id")

    # No explicit id → resolve the group by the workload name (resops-<name>-vg),
    # so the workshop declares only `name`. `vm_group_id` stays an optional override
    # for gating an arbitrary, differently-named group.
    if not group_id:
        group_id, gerr = find_vmgroup_id(client, vm_name)
        if gerr:
            return Reads(vm_name=vm_name, vmgroup_error=f"could not list VM groups: {gerr}")
        if not group_id:
            return Reads(vm_name=vm_name,
                         vmgroup_error=f"no VM group {vmgroup_name(vm_name)!r} — run `op protect` "
                                       "(or set workload.vm_group_id to gate an existing group)")

    vmgroup, vmgroup_error = _get(client, f"V4/VMGroup/{group_id}")
    vm, vm_error = _find_vm(client, vm_name)
    attestation, attestation_error = _attest(client, vm, workload.get("attestation_file"))
    # Proof comes FROM the attestation, not from a search of vendor job history.
    # The drill recorded the job it ran; we look that one up and confirm it. See
    # reads._recovery_proof for the download that satisfied the old search.
    proof, proof_error = _recovery_proof(client, attestation)
    return Reads(
        vm_name=vm_name,
        vmgroup=vmgroup, vmgroup_error=vmgroup_error,
        vm=vm, vm_error=vm_error,
        attestation=attestation, attestation_error=attestation_error,
        proof=proof, proof_error=proof_error,
    )


def _attest(client: Client, vm: dict | None,
            attestation_file: str | None = None) -> tuple[dict | None, str]:
    """Ask the attesters, strongest first, whether this recovery point is trustworthy.

    Order is deliberate. A NEGATIVE always wins: if the threat lane saw something,
    that outranks any local pass. Otherwise we fall back to the restore-verify
    attestation, which is the only source that can honestly say YES — because it
    opened the recovery point and read the data.

    restore-verify is opt-in: a workload must point at its file
    (workload.attestation_file). Absent, nobody has attested anything, and the
    Scan rung says so rather than inventing a pass."""
    if vm is None:
        return None, ""            # Recover already blocks; don't double-report

    # The VM's own /VM record carries its CommCell pseudo-client id at
    # client.clientId — distinct from pseudoClient.clientId, the hypervisor.
    client_id = (vm.get("client") or {}).get("clientId")
    if not client_id:
        return None, "VM record carries no CommCell client id"
    body, err = _get(client, "Client/Anomaly")
    if err:
        return None, err
    threat = threat_attestation(body, client_id)
    if threat is not None:
        return threat, ""          # a real negative outranks a local pass

    return _restore_verify_attestation(attestation_file)


def _restore_verify_attestation(path: str | None) -> tuple[dict | None, str]:
    """Read the attestation the restore drill wrote, if this workload declares one.

    The write lane produces it (drills/run_restore.py); the read lane consumes it
    only when told to. That keeps the coupling explicit and opt-in — the same
    shape as the offline demo's `fixture:` — instead of a hidden convention.
    `clean: null` means the drill could not verify, which is not a pass."""
    if not path:
        return None, ""
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        return None, ""            # no drill has run yet — unattested, not failed
    try:
        data = json.loads(p.read_text())
    except (OSError, ValueError) as err:
        return None, f"attestation file unreadable: {err}"
    if data.get("clean") is None:
        return None, ""            # the drill ran but could not verify
    return data, ""


def _lag(seconds: float) -> str:
    """A gap, in the unit a tired person can act on.

    Rounding a two-minute gap to "0.0h" reads as a bug rather than a fact, and it
    happened the first time this message fired live. The number matters — two
    minutes and two days say very different things about a team's cadence — so
    pick the unit rather than dropping it.
    """
    if seconds < 3600:
        return f"{round(seconds / 60)} min"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"


def _clip(text: str) -> str:
    """Trim a long API error to one line — at a word boundary, not mid-word."""
    if len(text) <= SUMMARY_CLIP:
        return text
    cut = text[:SUMMARY_CLIP]
    if " " in cut:
        cut = cut[:cut.rfind(" ")]
    return cut + " …"


def classify(reads: Reads) -> Ladder:
    """Walk the stages in order; stop at the first that doesn't clear. Pure."""
    rungs: list[Rung] = []

    def stop(state: State, stage: str, reason: str, evidence: dict, *, error: bool) -> Ladder:
        rungs.append(Rung(stage, _state_after(stage), False, reason, evidence))
        for later in STAGES[STAGES.index(stage) + 1:]:
            rungs.append(Rung(later, _state_after(later), None, "not reached", {}))
        return Ladder(state, stage, reason, error, rungs)

    def cleared(stage: str, summary: str, evidence: dict) -> None:
        rungs.append(Rung(stage, _state_after(stage), True, summary, evidence))

    vm_name = reads.vm_name
    if not vm_name:
        return stop(State.UNDISCOVERED, "Discover",
                    "config.workload.vm_name is not set", {}, error=True)

    # ── Discover ── is the VM onboarded into a protection group? ──────────────
    if reads.vmgroup_error:
        return stop(State.UNDISCOVERED, "Discover",
                    f"could not read VM group: {reads.vmgroup_error}",
                    {"vm_name": vm_name}, error=True)
    group = reads.vmgroup or {}
    group_name = group.get("name", "")
    vms = _vms_in_group(group)
    discover_ev = {"vm_name": vm_name, "group_name": group_name, "vms_in_group": len(vms)}
    if vm_name not in vms:
        return stop(State.UNDISCOVERED, "Discover",
                    f"{vm_name} not found in group {group_name!r}", discover_ev, error=False)
    cleared("Discover", f"onboarded — in {group_name!r}", discover_ev)

    # ── Protect ── is a protection plan attached? ─────────────────────────────
    plan = _plan_name(group)
    info = group.get("vmBackupInfo", {})
    protect_ev = {
        "plan": plan,
        "vmProtectedCount": info.get("vmProtectedCount", 0),
        "vmNotProtectedCount": info.get("vmNotProtectedCount", 0),
        "vmTotalCount": info.get("vmTotalCount", 0),
    }
    if not plan:
        return stop(State.DISCOVERED, "Protect",
                    f"in {group_name!r} but no protection plan attached", protect_ev, error=False)
    cleared("Protect", f"plan {plan} attached", protect_ev)

    # ── Detect ── did the last backup complete cleanly? ───────────────────────
    last_backup = group.get("lastBackup", {})
    status = last_backup.get("status", "")
    failure = last_backup.get("failureReason", "")
    detect_ev = {"last_backup_status": status, "last_backup_failure": failure,
                 "last_backup_job_id": last_backup.get("jobId")}
    if not status:
        return stop(State.PROTECTED, "Detect", "no backup has run yet", detect_ev, error=False)
    if failure or status != "COMPLETED":
        return stop(State.PROTECTED, "Detect",
                    f"last backup not clean — {_clip(failure or f'status {status}')}",
                    detect_ev, error=False)
    cleared("Detect", "last backup completed cleanly", detect_ev)

    # ── Recover ── recent, recoverable, SLA-Protected recovery point? ─────────
    if reads.vm_error:
        return stop(State.MONITORED, "Recover",
                    f"could not read VMs: {reads.vm_error}", {"vm_name": vm_name}, error=True)
    vm = reads.vm
    if vm is None:
        return stop(State.MONITORED, "Recover",
                    f"{vm_name} not found among protected VMs", {"vm_name": vm_name}, error=False)
    sla = vm.get("slaCategoryDescription", "")
    restore_enabled = vm.get("isRestoreActivityEnabled", False)
    last_success = vm.get("lastSuccessfulBackupTime", 0)
    recover_ev = {"sla_status": sla, "restore_enabled": restore_enabled,
                  "last_successful_backup_time": last_success, "vm_guid": vm.get("strGUID")}
    if not last_success:
        return stop(State.MONITORED, "Recover",
                    "no successful backup — nothing to recover from. Fix: run a backup",
                    recover_ev, error=False)
    if not restore_enabled:
        return stop(State.MONITORED, "Recover",
                    "restore activity is disabled for this VM", recover_ev, error=False)
    # "N/A" (slaStatus 3) means Commvault has NOT EVALUATED SLA for this VM yet.
    # That is a different fact from "SLA missed", and it needs a different fix, so
    # it gets its own message. A freshly protected workload sits here until the
    # periodic SLA calculation runs — proven live 2026-08-12: aug12-narwhal was
    # N/A with a successful backup 12 minutes old, while three DELETED VMs in the
    # same tenant still read "Protected".
    # It still BLOCKS. An unevaluated SLA is not a met one, and inventing a pass
    # here is the exact failure this ladder exists to refuse.
    if sla in ("", "N/A"):
        return stop(State.MONITORED, "Recover",
                    "SLA not evaluated yet (N/A) — Commvault has not run its periodic "
                    "SLA calculation for this workload; this is not a missed SLA",
                    recover_ev, error=False)
    if sla != "Protected":
        return stop(State.MONITORED, "Recover",
                    f"SLA not met — {sla}", recover_ev, error=False)
    cleared("Recover", "recoverable — SLA Protected", recover_ev)

    # ── Scan ── has ANYONE attested the point we'd restore from? ──────────────
    # An unattested recovery point is not a clean one. This rung used to clear on
    # the absence of a recorded anomaly, which sounds reasonable and is wrong: a
    # scan that never ran also records no anomaly. An attester must say something
    # it actually checked, or this rung blocks.
    #
    # 2026-08-12: a real scan finally reported a real detection here, so the rung
    # now has two working attesters instead of one. It changes nothing above. A
    # signal that arrives is a negative you can trust; a signal that is silent
    # still attests nothing.
    if reads.attestation_error:
        return stop(State.RECOVERABLE, "Scan",
                    f"could not read attestation: {reads.attestation_error}",
                    {"vm_name": vm_name}, error=True)
    attestation = reads.attestation
    if attestation is None:
        return stop(State.RECOVERABLE, "Scan",
                    "recovery point is UNATTESTED — nothing has verified it is safe "
                    "to restore from. Fix: run a restore drill",
                    {"vm_name": vm_name, "attested_by": None},
                    error=False)
    attested_at = attestation.get("at")
    newest_point = vm.get("lastSuccessfulBackupTime") or 0
    scan_ev = {"attested_by": attestation.get("source"),
               "attested_clean": attestation.get("clean"),
               "detail": attestation.get("detail", ""),
               "attested_at": attested_at,
               "newest_recovery_point": newest_point}
    if not attestation.get("clean"):
        return stop(State.RECOVERABLE, "Scan",
                    f"recovery point failed {attestation.get('source')} — "
                    f"{attestation.get('detail', 'not clean')}",
                    scan_ev, error=False)

    # ── COVERAGE ── does this attestation actually describe the point we would
    # restore from? An attestation is a claim about ONE recovery point, not a
    # property of the workload. We used to judge it by age alone, and on
    # 2026-08-12 that let a clean attestation written at 05:21 vouch for a
    # recovery point taken at 06:12 holding two EICAR files and fourteen
    # encrypted ones. The gate returned PROMOTE and wrote a framework-mapped
    # report saying so.
    #
    # AGE is policy and belongs to the gate (tiers.yaml). COVERAGE is
    # capability and belongs here: a newer recovery point that nothing has
    # opened is simply unverified, whatever the clock says. Comparing two
    # timestamps we already hold keeps classify() pure.
    #
    # This is strict on purpose. Every new backup leaves the newest point
    # unverified until a drill runs, which is TRUE and is what `enforce_from`
    # exists to let a team declare rather than hide.
    if not isinstance(attested_at, (int, float)):
        return stop(State.RECOVERABLE, "Scan",
                    f"attestation from {attestation.get('source')} carries no "
                    f"timestamp, so it cannot be shown to cover any recovery point",
                    scan_ev, error=False)
    if newest_point and attested_at < newest_point:
        return stop(State.RECOVERABLE, "Scan",
                    f"attestation does not cover the newest recovery point — "
                    f"verified {_lag(newest_point - attested_at)} before it was taken; "
                    f"re-run the drill", scan_ev, error=False)
    cleared("Scan", f"attested clean by {attestation.get('source')}", scan_ev)

    # ── Validate ── has a real restore PROVEN recovery for this VM? ───────────
    if reads.proof_error:
        return stop(State.RECOVERABLE, "Validate",
                    f"could not confirm the restore job: {reads.proof_error}",
                    {"vm_name": vm_name}, error=True)
    proof = reads.proof
    if proof is None:
        return stop(State.RECOVERABLE, "Validate",
                    f"recovery never proven for {vm_name}. Fix: run a restore drill",
                    {"vm_name": vm_name}, error=False)
    job_id = proof.get("jobId")
    pstatus = proof.get("status", "")
    validate_ev = {"last_drill_job": job_id, "status": pstatus}
    if pstatus != "Completed":
        return stop(State.RECOVERABLE, "Validate",
                    f"last restore not clean — job {job_id} {pstatus}", validate_ev, error=False)
    cleared("Validate", f"recovery proven — job {job_id}", validate_ev)

    return Ladder(State.VALIDATED, None, f"recovery proven — job {job_id}", False, rungs)


def _state_after(stage: str) -> State:
    """The rung a stage lifts you onto when it clears."""
    return (State.DISCOVERED, State.PROTECTED, State.MONITORED,
            State.RECOVERABLE, State.TRUSTED, State.VALIDATED)[STAGES.index(stage)]


# --------------------------------------------------------------------------- #
# Improve — the cross-cutting trend: did the rung move since last run? (pure)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Trend:
    """How this run's state compares to history. `regressed` feeds the gate —
    a workload that dropped a rung must not promote even if still VALIDATED-ish."""
    direction: str                # "climbed" | "held" | "regressed" | "baseline"
    summary: str                  # one human line
    previous: State | None        # the last comparable state (None on baseline)
    runs: int                     # total runs including this one
    regressed: bool               # True only when the rung dropped


def _state_of(entry: dict) -> State | None:
    """The recorded state of a past run, or None for legacy entries that predate
    the ladder (they stored per-function outcomes, not a state — not comparable)."""
    name = entry.get("state")
    return State[name] if name in State.__members__ else None


def trend(current: State, history: list) -> Trend:
    """Compare current state to the most recent comparable run. Pure — no clock."""
    runs = len(history) + 1
    prior = [s for s in (_state_of(e) for e in history) if s is not None]
    if not prior:
        return Trend("baseline", f"baseline on the readiness ladder (run {runs})",
                     None, runs, regressed=False)

    previous = prior[-1]
    if current.rank > previous.rank:
        return Trend("climbed", f"climbed {previous}→{current}", previous, runs, regressed=False)
    if current.rank < previous.rank:
        return Trend("regressed", f"regressed {previous}→{current}", previous, runs, regressed=True)
    # Held — count the consecutive trailing runs already at this state.
    streak = 1
    for s in reversed(prior):
        if s is current:
            streak += 1
        else:
            break
    return Trend("held", f"held at {current} over {streak} runs", previous, runs, regressed=False)
