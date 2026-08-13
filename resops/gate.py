"""
Continuous Service — the promotion gate (the 5th ResOps function).

The ladder *establishes* the workload's state; this is the *decision* that
consumes it at the prod boundary. It mutates nothing.

One question: is it safe to promote? With the ladder it's almost trivial —

    PROMOTE only if the workload reached VALIDATED, and the proof is fresh.

Everything below VALIDATED is a HOLD that names the rung you're stuck on. On top
of "reached VALIDATED" the gate adds the policy that capability can't express:
freshness (proof age), optional numeric RPO/RTO bars, and regression since the
last run. Stale-but-otherwise-clean proof is the only HOLD a human may
consciously override (--allow-stale), recorded as acknowledged risk.

Pure: it reads a Ladder plus already-measured numbers (age/rpo/rto, computed at
the I/O edge where the clock lives) and returns a verdict. No network, no clock.

`tolerated()` at the bottom is the ratchet — the ONE thing here that softens a
verdict, and it deliberately softens the aggregate only, never the workload.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .state import Ladder, State

# Default freshness SLA if config doesn't declare one. RPO has NO default
# threshold on purpose — we lean on Commvault's own SLA verdict (reaching
# RECOVERABLE) and only add a numeric bar if the user declares `rpo_target_hours`.
DEFAULT_PROOF_MAX_AGE_DAYS = 7


@dataclass(frozen=True)
class GateVerdict:
    """The promotion decision. decision is PROMOTE | HOLD | OVERRIDE."""
    decision: str
    reasons: list = field(default_factory=list)   # plain lines; empty when PROMOTE
    acknowledged_risk: dict | None = None          # set only on OVERRIDE

    @property
    def exit_code(self) -> int:
        """0 = ship (PROMOTE/OVERRIDE), 1 = HOLD. Config/auth errors are 2 elsewhere."""
        return 1 if self.decision == "HOLD" else 0

    def to_dict(self) -> dict:
        out = {"decision": self.decision, "reasons": self.reasons}
        if self.acknowledged_risk is not None:
            out["acknowledged_risk"] = self.acknowledged_risk
        return out


def gate(ladder: Ladder, policy: dict | None = None, *,
         allow_stale: bool = False, run_at: str = "",
         proof_age_days: float | None = None,
         attestation_age_days: float | None = None,
         rpo_hours: float | None = None,
         rto_minutes: float | None = None,
         sla_evaluated: bool | None = None,
         regressed: bool = False) -> GateVerdict:
    """Judge a workload's ladder for promotion. Pure.

    The measured numbers (proof_age_days, rpo_hours, rto_minutes) are supplied by
    the caller — classify() stays clock-free, so freshness is decided here.
    `regressed` comes from the Improve trend (did the state drop since last run).
    """
    policy = policy or {}
    max_age = policy.get("recovery_proof_max_age_days", DEFAULT_PROOF_MAX_AGE_DAYS)
    rpo_target = policy.get("rpo_target_hours")     # None = lean on Commvault's SLA verdict
    rto_target = policy.get("rto_target_minutes")   # None = don't enforce a recovery-time bar

    # Below the top rung → HOLD, naming exactly where the climb stopped.
    if ladder.state is not State.VALIDATED:
        return GateVerdict("HOLD", [f"stuck at {ladder.state}: {ladder.reason}"])

    # At VALIDATED: apply promotion-grade policy on top of proven recoverability.
    hard: list[str] = []
    # A stale attestation is a HARD block, not an overridable one. "We verified
    # this a year ago" says nothing about the point you would restore TODAY —
    # unlike aged recovery proof, which at least proved the mechanism works. The
    # bar is declared per tier (tiers.yaml attestation_max_age_days); undeclared
    # means unenforced, and the age is recorded in evidence either way.
    attest_max_age = policy.get("attestation_max_age_days")
    if (attest_max_age is not None and attestation_age_days is not None
            and attestation_age_days > attest_max_age):
        hard.append(f"attestation stale ({attestation_age_days}d > {attest_max_age}d) "
                    f"— nothing has verified this recovery point recently")
    if rpo_target is not None and rpo_hours is not None and rpo_hours > rpo_target:
        hard.append(f"rpo {rpo_hours}h > target {rpo_target}h")
    # NOTHING CAN JUDGE RECENCY HERE, so refuse rather than promote an age nobody
    # checked. The Recover rung used to block on an unevaluated vendor SLA; it no
    # longer does, because that verdict is a cached batch result — absent for ~30
    # minutes on every new workload, and stale-"Protected" on VMs deleted from
    # Azure. With it gone, the numeric bar is the only recency control left, and a
    # workload that declares no tier has neither. Say so, and name the fix.
    # `None` means the caller did not supply the fact, which is not the same as
    # False, so it does not block.
    if rpo_target is None and sla_evaluated is False:
        hard.append("recency cannot be judged — no rpo_target_hours declared and the "
                    "vendor has not evaluated SLA. Fix: declare a tier in config/tiers.yaml")
    if rto_target is not None and rto_minutes is not None and rto_minutes > rto_target:
        hard.append(f"rto {rto_minutes}m > target {rto_target}m")
    if regressed:
        hard.append("regression since last run")

    stale_reason = None
    if proof_age_days is not None and proof_age_days > max_age:
        stale_reason = f"recovery_proof_stale ({proof_age_days}d > {max_age}d)"

    # Hard blocks always HOLD (and carry staleness along for the record).
    if hard:
        return GateVerdict("HOLD", hard + ([stale_reason] if stale_reason else []))
    # Stale alone is the one consciously-overridable HOLD.
    if stale_reason:
        if allow_stale:
            risk = {"type": "stale_recovery_proof", "detail": stale_reason, "at": run_at}
            return GateVerdict("OVERRIDE", [stale_reason], acknowledged_risk=risk)
        return GateVerdict("HOLD", [stale_reason,
                                    "fix: run a drill, or --allow-stale (logged)"])
    return GateVerdict("PROMOTE", [])


# --------------------------------------------------------------------------- #
# The ratchet — declared, expiring enforcement tolerance.
# --------------------------------------------------------------------------- #
def tolerated(enforce_from: str, today: str) -> bool:
    """Is this workload inside a declared, unexpired enforcement tolerance?

    THE ADOPTION PROBLEM THIS SOLVES. Switch the gate on across a real estate and
    almost everything HOLDs, correctly, on day one. Nobody can ship, so the check
    gets deleted by Friday and the only tool that told the truth is gone. You do
    not turn on 100% coverage enforcement against a legacy codebase either. You
    ratchet.

    WHY THIS IS NOT A BYPASS. A bypass hides a gap. This hides nothing:

        the workload's own verdict   UNCHANGED — a HOLD is still a HOLD, on
                                     screen, in the bundle, in the report
        the aggregate exit code      excludes it, because that is the only thing
                                     that blocks a pipeline
        the count                    published as resops_tolerated, so "we have
                                     3 unenforced" is a number that must go down

    WHY IT IS A DATE AND NOT A FLAG. A boolean tolerance is permanent the moment
    someone forgets it. A date cannot be: the day arrives whether or not anyone
    revisits it, and the workload starts enforcing on its own. That is the whole
    ratchet, in one field that cannot be left open-ended.

    Both arguments are ISO YYYY-MM-DD. `today` is passed in rather than read, so
    this module keeps its no-clock promise. A malformed date raises ValueError:
    a typo must fail LOUD, because the failure mode of failing quiet here is
    tolerating a workload forever."""
    return date.fromisoformat(today) < date.fromisoformat(enforce_from)
