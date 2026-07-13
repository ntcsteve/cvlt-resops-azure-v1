"""Tests for tier → gate policy resolution.

Covers _resolve_policy() in __main__ (the tier-wiring glue) and the full gate
path with tier-injected bars, verifying that tiers.yaml is the authoritative
source of RPO/RTO targets when a workload declares a tier.
"""
from resops.__main__ import _resolve_policy
from resops.gate import gate
from resops.state import Ladder, State


def _ladder(state, *, reason="", blocked=None):
    return Ladder(state, blocked, reason or str(state), False, [])


VALIDATED = _ladder(State.VALIDATED, reason="recovery proven — job 7540314")


# --------------------------------------------------------------------------- #
# _resolve_policy — tier bar injection
# --------------------------------------------------------------------------- #

def test_no_tier_returns_base_policy():
    workload = {"name": "vm01"}
    config = {"gate": {"recovery_proof_max_age_days": 14}}
    policy = _resolve_policy(workload, config)
    assert policy["recovery_proof_max_age_days"] == 14
    assert "rpo_target_hours" not in policy
    assert "rto_target_minutes" not in policy


def test_tier1_injects_rpo_and_rto():
    workload = {"name": "vm01", "tier": "tier1"}
    policy = _resolve_policy(workload, {})
    # tier1 in tiers.yaml: rpo_hours=8, rto_minutes=240
    assert policy["rpo_target_hours"] == 8
    assert policy["rto_target_minutes"] == 240


def test_tier2_injects_relaxed_bars():
    workload = {"name": "vm01", "tier": "tier2"}
    policy = _resolve_policy(workload, {})
    assert policy["rpo_target_hours"] == 24
    assert policy["rto_target_minutes"] == 480


def test_explicit_gate_rpo_overrides_tier():
    """A hand-declared rpo_target_hours in config.gate beats the tier's bar."""
    workload = {"name": "vm01", "tier": "tier1"}
    config = {"gate": {"rpo_target_hours": 4}}   # tighter than tier1's 8h
    policy = _resolve_policy(workload, config)
    assert policy["rpo_target_hours"] == 4        # explicit wins


def test_workload_promote_policy_overrides_tier():
    """promote_policy sets the base; tier still fills any gaps not declared in it."""
    workload = {"name": "vm01", "tier": "tier1", "promote_policy": {"rpo_target_hours": 2}}
    policy = _resolve_policy(workload, {})
    assert policy["rpo_target_hours"] == 2          # explicit wins over tier1's 8h
    assert policy["rto_target_minutes"] == 240      # tier1 fills the gap promote_policy left


def test_unknown_tier_does_not_crash(capsys):
    workload = {"name": "vm01", "tier": "tier99"}
    policy = _resolve_policy(workload, {"gate": {"recovery_proof_max_age_days": 7}})
    out = capsys.readouterr().out
    assert "tier99" in out and "not found" in out
    assert "rpo_target_hours" not in policy       # unknown tier → no bars, no crash
    assert policy.get("recovery_proof_max_age_days") == 7


# --------------------------------------------------------------------------- #
# End-to-end gate behaviour with tier bars
# --------------------------------------------------------------------------- #

def test_tier1_rpo_breach_holds_gate():
    """tier1 sets rpo_target_hours=8; proof 9h old → HOLD."""
    workload = {"name": "vm01", "tier": "tier1"}
    policy = _resolve_policy(workload, {})
    v = gate(VALIDATED, policy, proof_age_days=1, rpo_hours=9.0)
    assert v.decision == "HOLD"
    assert "9.0h > target 8h" in v.reasons[0]


def test_tier1_rpo_ok_promotes():
    workload = {"name": "vm01", "tier": "tier1"}
    policy = _resolve_policy(workload, {})
    v = gate(VALIDATED, policy, proof_age_days=1, rpo_hours=7.5)
    assert v.decision == "PROMOTE"


def test_tier2_same_rpo_promotes():
    """9h RPO is fine for tier2 (target=24h) but holds tier1 (target=8h)."""
    workload = {"name": "vm01", "tier": "tier2"}
    policy = _resolve_policy(workload, {})
    v = gate(VALIDATED, policy, proof_age_days=1, rpo_hours=9.0)
    assert v.decision == "PROMOTE"


def test_tier1_rto_breach_holds_gate():
    """tier1 rto_target_minutes=240; restore took 300m → HOLD."""
    workload = {"name": "vm01", "tier": "tier1"}
    policy = _resolve_policy(workload, {})
    v = gate(VALIDATED, policy, proof_age_days=1, rto_minutes=300.0)
    assert v.decision == "HOLD"
    assert "300.0m > target 240m" in v.reasons[0]


def test_tier_freshness_still_enforced():
    """Tier injection doesn't bypass the freshness check."""
    workload = {"name": "vm01", "tier": "tier2"}
    policy = _resolve_policy(workload, {"gate": {"recovery_proof_max_age_days": 7}})
    v = gate(VALIDATED, policy, proof_age_days=30, rpo_hours=1.0)
    assert v.decision == "HOLD"
    assert "recovery_proof_stale" in v.reasons[0]
