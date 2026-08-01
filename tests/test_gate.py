"""Unit tests for the promotion gate (Continuous Service) — no live tenant.

The gate now reads a Ladder + measured numbers. We build Ladders directly (gate
only reads .state and .reason) and pass age/rpo/rto/regressed as the caller would.
"""
from resops.gate import gate
from resops.state import Ladder, State


def _ladder(state, *, reason="", blocked=None):
    """A minimal Ladder — the gate only reads .state and .reason."""
    return Ladder(state, blocked, reason or str(state), False, [])


VALIDATED = _ladder(State.VALIDATED, reason="recovery proven — job 7540314")


def test_validated_and_fresh_promotes():
    v = gate(VALIDATED, proof_age_days=1)
    assert v.decision == "PROMOTE"
    assert v.exit_code == 0
    assert v.reasons == []


def test_below_validated_holds_and_names_the_rung():
    v = gate(_ladder(State.MONITORED, reason="SLA not met — Missed SLA", blocked="Recover"))
    assert v.decision == "HOLD"
    assert v.exit_code == 1
    assert "stuck at MONITORED" in v.reasons[0]
    assert "SLA not met" in v.reasons[0]


def test_recoverable_but_unproven_holds():
    v = gate(_ladder(State.RECOVERABLE, reason="recovery never proven for vm01", blocked="Validate"))
    assert v.decision == "HOLD"
    assert "stuck at RECOVERABLE" in v.reasons[0]
    assert "never proven" in v.reasons[0]


def test_rpo_over_target_holds_only_when_declared():
    assert gate(VALIDATED, proof_age_days=1, rpo_hours=9.0).decision == "PROMOTE"  # no target
    v = gate(VALIDATED, {"rpo_target_hours": 6}, proof_age_days=1, rpo_hours=9.0)
    assert v.decision == "HOLD"
    assert "9.0h > target 6h" in v.reasons[0]


def test_rto_over_target_holds_only_when_declared():
    assert gate(VALIDATED, proof_age_days=1, rto_minutes=90).decision == "PROMOTE"  # no target
    v = gate(VALIDATED, {"rto_target_minutes": 60}, proof_age_days=1, rto_minutes=90)
    assert v.decision == "HOLD"
    assert "90m > target 60m" in v.reasons[0]


def test_regression_holds():
    v = gate(VALIDATED, proof_age_days=1, regressed=True)
    assert v.decision == "HOLD"
    assert "regression" in v.reasons[0]


def test_stale_proof_holds_by_default():
    v = gate(VALIDATED, {"recovery_proof_max_age_days": 7}, proof_age_days=12)
    assert v.decision == "HOLD"
    assert "recovery_proof_stale (12d > 7d)" in v.reasons[0]
    assert v.acknowledged_risk is None


def test_stale_proof_overridable():
    v = gate(VALIDATED, {"recovery_proof_max_age_days": 7},
             allow_stale=True, run_at="2026-06-13T00:00:00Z", proof_age_days=12)
    assert v.decision == "OVERRIDE"
    assert v.exit_code == 0
    assert v.acknowledged_risk["type"] == "stale_recovery_proof"
    assert v.acknowledged_risk["at"] == "2026-06-13T00:00:00Z"


def test_allow_stale_does_not_excuse_a_real_block():
    """Override only forgives staleness — a hard block still HOLDs."""
    v = gate(VALIDATED, {"recovery_proof_max_age_days": 7},
             allow_stale=True, proof_age_days=12, regressed=True)
    assert v.decision == "HOLD"


def test_allow_stale_does_not_excuse_being_below_validated():
    """You can't --allow-stale your way past an unproven workload."""
    v = gate(_ladder(State.RECOVERABLE, blocked="Validate"), allow_stale=True)
    assert v.decision == "HOLD"


def test_default_freshness_applies_without_policy():
    assert gate(VALIDATED, proof_age_days=99).decision == "HOLD"      # default 7d
    assert gate(VALIDATED, proof_age_days=3).decision == "PROMOTE"


# --------------------------------------------------------------------------- #
# Attestation freshness — "somebody checked, once, a year ago" is not a pass.
#
# The ladder answers WHETHER a recovery point was attested. It cannot answer
# WHEN, because classify() is clock-free. Without this bar, an attestation from
# ten minutes ago and one from last year are indistinguishable — which is the
# same false-clean trap we spent 2026-08-01 removing, wearing different clothes.
# --------------------------------------------------------------------------- #
def test_stale_attestation_holds():
    v = gate(VALIDATED, {"attestation_max_age_days": 30},
             proof_age_days=1, attestation_age_days=400)
    assert v.decision == "HOLD"
    assert "attestation stale" in v.reasons[0]
    assert "400" in v.reasons[0]


def test_fresh_attestation_promotes():
    v = gate(VALIDATED, {"attestation_max_age_days": 30},
             proof_age_days=1, attestation_age_days=3)
    assert v.decision == "PROMOTE"


def test_attestation_age_is_unenforced_unless_declared():
    # Same deliberate choice as RPO: no declared bar means no bar. The age still
    # rides along in the evidence bundle, so the gap stays visible.
    v = gate(VALIDATED, {}, proof_age_days=1, attestation_age_days=9999)
    assert v.decision == "PROMOTE"


def test_stale_attestation_is_NOT_overridable():
    # Aged recovery proof at least proved the mechanism works, so --allow-stale
    # can consciously accept it. A stale attestation says nothing about the point
    # you would restore today. There is no override, on purpose.
    v = gate(VALIDATED, {"attestation_max_age_days": 30},
             proof_age_days=1, attestation_age_days=400, allow_stale=True)
    assert v.decision == "HOLD"


def test_stale_attestation_reported_alongside_other_blocks():
    v = gate(VALIDATED, {"attestation_max_age_days": 30, "rpo_target_hours": 8},
             proof_age_days=1, attestation_age_days=400, rpo_hours=99)
    assert v.decision == "HOLD"
    assert len(v.reasons) == 2
