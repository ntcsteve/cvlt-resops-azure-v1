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
"""
from __future__ import annotations

from dataclasses import dataclass, field

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
