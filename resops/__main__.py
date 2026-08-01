"""
The ResOps runner — five modes over the same read-only readiness ladder:

  python -m resops [config.yaml]          climb the ladder; exit = number of read FAILs
  python -m resops gate [config.yaml]     the promotion gate; exit 0 PROMOTE / 1 HOLD
  python -m resops list [config.yaml]     list VM groups + ids (onboarding lookup)
  python -m resops verify [config.yaml]   audit the hash-chained trail; exit 0 intact
  python -m resops metrics [config.yaml]  publish the last run as Prometheus text

`verify` and `metrics` read what a previous run wrote — no tenant, no network.

Each workload is placed on ONE rung of the readiness ladder —
UNDISCOVERED → DISCOVERED → PROTECTED → MONITORED → RECOVERABLE → TRUSTED →
VALIDATED —
by classify() (resops/state.py). The runner gathers the reads, prints the rung,
the stage it's blocked on, and the trend since last run, then writes the evidence
bundle + audit trail. `gate` is Continuous Service: promote only if the workload
reached VALIDATED and the proof is fresh. Add --allow-stale to ship on aged-but-
clean proof (logged as acknowledged risk). Add --detail for the per-stage rows.
Nothing here mutates your environment.

Config declares one `workload:` or a `workloads:` list (a resilience programme
across critical functions). Each workload keeps its own evidence subdir + hash
chain; a top-level summary.json rolls them up. The gate HOLDs if ANY workload
isn't VALIDATED — criticality is recorded as evidence, never a way to ship past it.

The one exception is `enforce_from:` — a declared, dated enforcement tolerance
(see gate.tolerated). It never changes a workload's own verdict, only whether
that verdict blocks the aggregate exit code, and it expires by itself.
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import json
import sys
import time
from pathlib import Path

import yaml

from .assurance.controls import load_controls
from .assurance.findings import track_findings
from .assurance.junit import write_junit
from .assurance.metrics import render_metrics
from .assurance.report import write_report
from .client import AuthError, Client, load_credentials
from .config import load_tiers, platform_url
from .evidence import (
    DEVOPS_LENS, Bundle, append_history, history_entry, load_history, verify_history,
)
from .gate import gate, tolerated
from .reads import (_age_days, _attestation_age_days, _rpo_hours, _rto_minutes,
                    list_vmgroups)
from .render import (
    DIM, GREEN, RED, YELLOW, color, ladder_to_results, render_detail, render_headline,
    render_vmgroups,
)
from .state import Reads, classify, gather, trend

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config" / "workshop.yaml"
ENV_PATH = ROOT / ".env"


def _resolve_ages(node, now: float):
    """Resolve `{"days_ago": N}` / `{"hours_ago": N}` anywhere in a fixture into an
    epoch. Everything else passes through untouched.

    Fixtures otherwise carry FIXED epochs, so a demo's displayed RPO and
    attestation age grow every week until they read as nonsense. Verdicts never
    rotted (config/estate.yaml pins its bars wide open on purpose) but the numbers
    did — and config/incident.yaml cannot work that way at all, because its whole
    exercise turns on "6 days ago" still meaning six days when you run it.

    Only a dict whose keys are EXACTLY one of these converts, so a real API payload
    can never be mistaken for an offset."""
    if isinstance(node, dict):
        for unit, seconds in (("days_ago", 86400), ("hours_ago", 3600)):
            if set(node) == {unit}:
                return int(now - node[unit] * seconds)
        return {k: _resolve_ages(v, now) for k, v in node.items()}
    if isinstance(node, list):
        return [_resolve_ages(item, now) for item in node]
    return node


def reads_from_fixture(rel_path: str) -> Reads:
    """Build Reads from a committed JSON fixture — the no-cloud demo path. This is
    the same Reads that gather() folds live API GETs into, so the demo drives the
    real ladder, gate, and crosswalk with zero network, token, or tenant. Unknown
    keys (e.g. a leading `_comment`) are ignored so fixtures can self-document.

    Reads the clock, but only here: this is an I/O boundary like gather(), and
    classify() downstream stays pure."""
    data = _resolve_ages(json.loads((ROOT / rel_path).read_text()), time.time())
    fields = {f.name for f in dataclasses.fields(Reads)}
    return Reads(**{k: v for k, v in data.items() if k in fields})

CONFIG_ERROR = 2  # exit code for bad config/auth, distinct from read FAILs / HOLD

# Subcommands that take over from the default ladder climb.
SUBCOMMANDS = ("gate", "verify", "list", "metrics")

USAGE = """resops — read-only resilience readiness ladder + promotion gate

Usage:
  python -m resops [config] [--detail]         climb the ladder (exit = number of read FAILs)
  python -m resops gate [config] [--allow-stale] [--detail]
                                               promotion gate (exit 0 PROMOTE / 1 HOLD)
  python -m resops list [config]               list VM groups + ids (confirm your workload's group)
  python -m resops verify [config]             audit the hash-chained trail (exit 0 intact)
  python -m resops metrics [config]            Prometheus exposition of the LAST run (stdout)
  python -m resops help                        show this message

config defaults to config/workshop.yaml. Nothing here mutates your environment.

Adopting the gate across an estate that isn't ready yet? Declare a dated
tolerance on a workload and its HOLD stops blocking the aggregate until then:

    enforce_from: 2027-01-01        # a DATE, so it expires on its own
    tolerance_reason: "..."         # recorded in the evidence bundle

The workload still HOLDs, on screen and in the report. Only the aggregate exit
code stops counting it, and `resops_tolerated` publishes how many you have."""


def die(message: str) -> int:
    print(color(message, RED))
    return CONFIG_ERROR


def _display(path: Path) -> str:
    """Path relative to the repo root for tidy output — or absolute if it lives
    outside the repo (e.g. a CI artifacts dir, where relative_to would crash)."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _looks_like_command(arg: str) -> bool:
    """A bare first word that isn't a config file — likely a mistyped subcommand."""
    return not arg.endswith((".yaml", ".yml")) and not Path(arg).exists()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    # Tiny hand-parse: help, then `gate`/`verify` subcommand + flags + optional config.
    if argv and argv[0] in ("help", "--help", "-h"):
        print(USAGE)
        return 0

    subcommand = argv[0] if argv and argv[0] in SUBCOMMANDS else None
    if subcommand:
        argv = argv[1:]
    elif argv and not argv[0].startswith("-") and _looks_like_command(argv[0]):
        print(USAGE)
        return die(f"\nUnknown command: {argv[0]}")
    gate_mode = subcommand == "gate"
    allow_stale = "--allow-stale" in argv
    detail = "--detail" in argv
    positional = [a for a in argv if not a.startswith("-")]
    config_path = Path(positional[0]) if positional else DEFAULT_CONFIG

    if not config_path.exists():
        return die(f"Missing config: {config_path}")
    config = yaml.safe_load(config_path.read_text()) or {}

    base_dir = ROOT / config.get("evidence_dir", "evidence")
    workloads, flat = _workloads(config)

    # Validate declared tiers early — fail with the fix before any API call.
    known_tiers = load_tiers()
    for w in workloads:
        t = w.get("tier")
        if t and t not in known_tiers:
            return die(f"workload '{w['name']}': tier '{t}' not in config/tiers.yaml"
                       f" — defined: {', '.join(known_tiers) or 'none'}")

    # Resolve each declared enforcement tolerance into a plain bool, here at the
    # I/O edge where the clock lives, so everything downstream (gate, aggregate,
    # metrics, report) reads a resolved value and stays clock-free.
    today = _dt.date.today().isoformat()
    for w in workloads:
        err = _resolve_tolerance(w, today)
        if err:
            return die(err)

    # `verify` and `metrics` both read what a previous run wrote — no tenant needed.
    if subcommand == "verify":
        return _verify(base_dir, workloads)
    if subcommand == "metrics":
        return _metrics(base_dir, workloads)

    # Offline demo: when every workload reads from a committed `fixture:`, no
    # tenant, token, or network is needed — the no-cloud "see it first" path. The
    # same classify → gate → crosswalk runs; only the reads are canned.
    offline = bool(workloads) and all(w.get("fixture") for w in workloads)

    if offline:
        target, client = "offline fixture — no cloud", None
    else:
        # The API URL has ONE live home: workshop.yaml's platform.web_service_url —
        # the single source both the read (resops) and write (op) lanes read, so
        # they can't drift onto different tenants.
        target = str(config.get("target") or platform_url() or "").rstrip("/")
        if not target.startswith(("http://", "https://")):
            return die(f"no API URL — set platform.web_service_url in config/workshop.yaml; got '{target}'")
        creds = load_credentials(ENV_PATH)
        if not creds.access_token:
            return die("CV_ACCESS_TOKEN not set — copy .env.example to .env")
        client = Client(target, creds, ENV_PATH)

    # `list` is the onboarding lookup — needs a live tenant.
    if subcommand == "list":
        if offline:
            return die("`list` needs a live tenant — this config is an offline fixture")
        return _list(client)

    if not workloads:
        return die("config must define a `workload:` or a `workloads:` list")

    try:
        controls = load_controls(config)   # crosswalk for the configured framework(s)
    except FileNotFoundError as err:
        return die(str(err))

    print(f"Target: {target}\n")
    run_at = _dt.datetime.now(_dt.timezone.utc).isoformat()

    summaries = []
    try:
        for w in workloads:
            w_dir = base_dir / _slug(w["name"])
            summaries.append(_run_one(client, config, w, controls, w_dir, run_at,
                                      target, gate_mode, allow_stale, detail, multi=not flat))
    except AuthError as err:
        return die(f"Auth failed: {err}")

    return _aggregate(summaries, base_dir, run_at, target, gate_mode, flat)


# --------------------------------------------------------------------------- #
# Workload resolution — a single `workload:` or a `workloads:` programme.
# --------------------------------------------------------------------------- #
def _resolve_policy(workload: dict, config: dict) -> dict:
    """Assemble the promotion gate policy.

    Priority (high → low):
      1. workload.promote_policy  — per-workload explicit override
      2. config.gate / config.promote_policy  — programme-level default
      3. tier bars from tiers.yaml  — auto-injected for any key NOT already declared

    Tier bars fill gaps; they never overwrite explicit declarations. Unknown tier
    names warn and continue — no tiers.yaml means no RPO/RTO bars (still enforces
    freshness and VALIDATED state).
    """
    base = dict(workload.get("promote_policy")
                or config.get("gate")
                or config.get("promote_policy")
                or {})
    tier_name = workload.get("tier")
    if tier_name:
        tier = load_tiers().get(tier_name)
        if not tier:
            # Defensive guard for direct callers (e.g. tests). main() validates
            # tiers early and die()s before reaching here, so this path is only
            # reachable when _resolve_policy is called outside the main flow.
            print(color(f"  warning: tier '{tier_name}' not found in tiers.yaml"
                        " — no RPO/RTO bars applied", YELLOW))
        else:
            if "rpo_target_hours" not in base and "rpo_hours" in tier:
                base["rpo_target_hours"] = tier["rpo_hours"]
            if "rto_target_minutes" not in base and "rto_minutes" in tier:
                base["rto_target_minutes"] = tier["rto_minutes"]
            if ("attestation_max_age_days" not in base
                    and "attestation_max_age_days" in tier):
                base["attestation_max_age_days"] = tier["attestation_max_age_days"]
    return base


def _resolve_tolerance(workload: dict, today: str) -> str:
    """Resolve `enforce_from:` into a plain `tolerated` bool on the workload.

    Returns an error message to die() on, or "" when fine. YAML parses an
    unquoted ISO date into a date object and a malformed one into a string, so
    str() normalises both and gate.tolerated() rejects whatever isn't a date."""
    declared = workload.get("enforce_from")
    if declared in (None, ""):
        workload["tolerated"] = False
        return ""
    try:
        workload["tolerated"] = tolerated(str(declared), today)
    except (ValueError, TypeError):
        return (f"workload '{workload['name']}': enforce_from '{declared}' is not a date"
                f" — expected YYYY-MM-DD, e.g. enforce_from: 2026-10-01")
    return ""


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-") or "workload"


def _normalize(w: dict) -> dict:
    # `name` is the codename declared in workshop.yaml; `vm_name` is what the reads
    # key off (the VM inside the group). For an op-created workload they're equal,
    # so accept either and fill the other.
    name = w.get("name") or w.get("vm_name") or "workload"
    return {**w, "name": name, "vm_name": w.get("vm_name") or name,
            "criticality": w.get("criticality", "unspecified"),
            "env": w.get("env", "unspecified"),
            "owner": w.get("owner", "unspecified")}


def _workloads(config: dict) -> tuple[list, bool]:
    """Return (workloads, flat). flat=True keeps the singular-config flat layout."""
    if config.get("workloads"):
        return [_normalize(w) for w in config["workloads"]], False
    single = config.get("workload")
    return ([_normalize(single)] if single else []), True


def _metrics(base_dir: Path, workloads: list) -> int:
    """Print the LAST run's evidence as Prometheus text. No tenant, no network.

    Deliberately does not re-judge: the gate already did that and wrote the
    answer down. Judge once, publish many — so a scheduled `resops gate` in CI
    can pipe this straight to a pushgateway without paying for a second pass, and
    so a dashboard can never disagree with the evidence bundle beside it."""
    summary_path = base_dir / "summary.json"
    if not summary_path.exists():
        return die(f"no run to publish: {_display(summary_path)} not found"
                   f" — run `resops gate` first")
    summary = json.loads(summary_path.read_text())

    bundles = []
    for w in workloads:
        bundle_path = base_dir / _slug(w["name"]) / "bundle.json"
        if bundle_path.exists():
            bundles.append(json.loads(bundle_path.read_text()))

    print(render_metrics(summary, bundles), end="")
    return 0


def _verify(base_dir: Path, workloads: list) -> int:
    paths = [base_dir / _slug(w["name"]) / "history.jsonl" for w in workloads]
    broken = []
    for p in paths:
        ok, where = verify_history(p)
        if not ok:
            broken.append((p, where))
    if not broken:
        print(color("  audit trail intact — hash chain verified", GREEN))
        return 0
    for path, where in broken:
        print(color(f"  TAMPERED — {_display(path)} breaks at entry {where}", RED))
    return 1


def _list(client) -> int:
    """The onboarding lookup — print every VM group + id to confirm a workload's group
    exists (resops resolves it by name; the id is only for the optional override).
    Read-only; needs target + token but no workload."""
    try:
        vmgroups, err = list_vmgroups(client)
    except AuthError as auth_err:
        return die(f"Auth failed: {auth_err}")
    if err:
        return die(f"could not list VM groups: {err}")
    for line in render_vmgroups(vmgroups):
        print(line)
    return 0


# --------------------------------------------------------------------------- #
# Climb one workload's ladder (and judge the gate, in gate mode).
# --------------------------------------------------------------------------- #
def _open_count(findings) -> str:
    n = sum(f.status == "OPEN" for f in findings)
    return f" · {n} open finding{'s' if n != 1 else ''}" if n else ""


def _run_one(client, config, workload, controls, w_dir, run_at, target,
             gate_mode, allow_stale, detail, multi) -> dict:
    history = load_history(w_dir / "history.jsonl")

    # Read once, classify to a state, compare to history — the whole ladder.
    # A canned `fixture:` (the offline demo) stands in for the live API reads.
    reads = (reads_from_fixture(workload["fixture"]) if workload.get("fixture")
             else gather(client, workload))
    ladder = classify(reads)
    tr = trend(ladder.state, history)

    # Numbers the clock-free classify() can't hold, measured here at the edge.
    metrics = {"rpo_hours": _rpo_hours(reads.vm),
               "proof_age_days": _age_days(reads.proof) if reads.proof else None,
               "attestation_age_days": _attestation_age_days(reads.attestation),
               "rto_minutes": _rto_minutes(reads.proof) if reads.proof else None}

    results = ladder_to_results(ladder, tr, metrics)
    stage_results = results[:-1]   # the 5 stages (improve is cross-cutting, not a finding)
    findings = track_findings(workload["name"], run_at, stage_results, history)

    verdict = None
    if gate_mode:
        policy = _resolve_policy(workload, config)
        verdict = gate(ladder, policy, allow_stale=allow_stale, run_at=run_at,
                       proof_age_days=metrics["proof_age_days"],
                       attestation_age_days=metrics["attestation_age_days"],
                       rpo_hours=metrics["rpo_hours"],
                       rto_minutes=metrics["rto_minutes"], regressed=tr.regressed)

    # A declared tolerance rides along in the evidence, never in the verdict.
    # An auditor must be able to see both what the gate decided and what the
    # programme chose not to enforce yet.
    gate_dict = verdict.to_dict() if verdict else None
    if gate_dict is not None and workload.get("enforce_from"):
        gate_dict["tolerance"] = {
            "enforce_from": str(workload["enforce_from"]),
            "active": workload.get("tolerated", False),
            "reason": workload.get("tolerance_reason", ""),
        }

    bundle = Bundle(target=target, run_at=run_at, results=results,
                    gate=gate_dict, controls=controls, findings=findings)
    paths = (w_dir / "bundle.json", w_dir / "history.jsonl", w_dir / "report.md")

    for line in render_headline(workload["name"], workload["criticality"], ladder, tr,
                                multi, rpo_hours=metrics["rpo_hours"],
                                env=workload.get("env", ""),
                                owner=workload.get("owner", "")):
        print(line)
    if detail:
        for line in render_detail(results):
            print(line)
    _finalize(bundle, stage_results, run_at, target, ladder.state.name, paths)
    write_junit(bundle.to_dict(), workload["name"], paths[0].parent / "junit.xml")

    if gate_mode:
        _print_verdict(verdict, paths[0],
                       str(workload.get("enforce_from") or ""),
                       workload.get("tolerated", False))
    elif not multi:
        print(f"  Evidence: {_display(paths[0])} · Report: {_display(paths[2])}"
              f"{_open_count(findings)}")
    if multi:
        print()
    return {
        "name": workload["name"], "criticality": workload["criticality"],
        "env": workload["env"], "owner": workload["owner"],
        "state": ladder.state.name,
        # Both already computed above; the summary is what the metrics lane reads,
        # so anything a dashboard needs has to survive into it.
        "blocked_stage": ladder.blocked_stage,
        "attestation_age_days": metrics["attestation_age_days"],
        "enforce_from": str(workload["enforce_from"]) if workload.get("enforce_from") else None,
        "tolerated": workload.get("tolerated", False),
        "evidence": _display(paths[0]),
        "counts": bundle.summary_counts(),
        "open_findings": sum(f.status == "OPEN" for f in findings),
        "gate": verdict.decision if verdict else None,
        "exit": verdict.exit_code if verdict else bundle.exit_code(),
    }


def _finalize(bundle, stage_results, run_at, target, state, paths) -> None:
    """Write the bundle, append the hash-chained history (with state), render the report."""
    bundle_path, history_path, report_path = paths
    bundle_dict = bundle.to_dict()
    bundle.write(bundle_path)
    append_history(history_path, history_entry(run_at, target, stage_results, state))
    write_report(bundle_dict, report_path)


def _print_verdict(verdict, bundle_path, enforce_from: str = "",
                   is_tolerated: bool = False) -> None:
    print("  " + "─" * 41)
    code = {"PROMOTE": GREEN, "OVERRIDE": YELLOW, "HOLD": RED}[verdict.decision]
    headline = verdict.reasons[0] if verdict.reasons else "recoverability proven"
    print(f"  {color(verdict.decision, code)}  {headline} · exit {verdict.exit_code}")
    print(color(f"  ↳ {DEVOPS_LENS['continuous_business']}", DIM))
    for extra in verdict.reasons[1:]:
        print(color(f"  ↳ {extra}", DIM))
    if verdict.acknowledged_risk:
        print(color(f"  ↳ {_display(bundle_path)}: acknowledged_risk logged", DIM))
    # The verdict above is the verdict. This line only says whether it currently
    # blocks the pipeline — printed loudly so a tolerance can never be quiet.
    if enforce_from and verdict.decision == "HOLD":
        if is_tolerated:
            print(color(f"  ↳ TOLERATED until {enforce_from} — still a HOLD, excluded "
                        f"from the aggregate until that date", YELLOW))
        else:
            print(color(f"  ↳ tolerance EXPIRED {enforce_from} — enforced from now on", RED))
    elif enforce_from and is_tolerated:
        print(color(f"  ↳ tolerance until {enforce_from} is no longer needed — "
                    f"this workload passes; remove enforce_from", DIM))


# --------------------------------------------------------------------------- #
# Roll the workloads up into one programme verdict + summary.json.
# --------------------------------------------------------------------------- #
def _aggregate(summaries, base_dir, run_at, target, gate_mode, flat) -> int:
    totals = {k: sum(s["counts"][k] for s in summaries) for k in ("pass", "gap", "fail", "skip")}
    opens = sum(s["open_findings"] for s in summaries)
    # THE RATCHET, and the only place it acts. A tolerated workload still holds —
    # it just doesn't block the pipeline yet. Both lists are published so the gap
    # is counted, never dropped.
    all_holds = [s for s in summaries if s["gate"] == "HOLD"]
    holds = [s["name"] for s in all_holds if not s.get("tolerated")]
    tolerated_holds = [s["name"] for s in all_holds if s.get("tolerated")]
    overridden = [s["name"] for s in summaries if s["gate"] == "OVERRIDE"]
    if gate_mode:
        exit_code, decision = (1, "HOLD") if holds else (0, "PROMOTE")
    else:
        exit_code, decision = sum(s["counts"]["fail"] for s in summaries), None

    summary = {
        "run_at": run_at, "target": target, "mode": "gate" if gate_mode else "loop",
        "workloads": summaries,
        "aggregate": {"decision": decision, "totals": totals, "open_findings": opens,
                      "overridden": overridden, "tolerated": tolerated_holds,
                      "exit": exit_code},
    }
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    if not flat:   # only roll up when it's a multi-workload programme
        n = len(summaries)
        tol = f" · {len(tolerated_holds)} TOLERATED ({', '.join(tolerated_holds)})" \
            if tolerated_holds else ""
        if gate_mode and decision == "HOLD":
            print(color(f"AGGREGATE  HOLD — {', '.join(holds)}{tol} · exit {exit_code}", RED))
        elif gate_mode:
            extra = f" ({len(overridden)} overridden)" if overridden else ""
            if tolerated_holds:
                # Not green. Nothing blocks the pipeline, but the estate is not clear
                # and the headline must not imply that it is.
                print(color(f"AGGREGATE  PROMOTE — {n - len(tolerated_holds)}/{n} enforced "
                            f"and clear{extra}{tol} · exit 0", YELLOW))
            else:
                print(color(f"AGGREGATE  PROMOTE — {n} workload(s) clear{extra} · exit 0", GREEN))
        else:
            states = ", ".join(f"{s['name']}={s['state']}" for s in summaries)
            print(f"AGGREGATE  {n} workload(s) · {states} · {opens} open · exit {exit_code}")
        print(f"Summary: {_display(base_dir / 'summary.json')}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
