"""Prometheus exposition — the fleet view, as data.

These pin the two things that would quietly rot: the rung→number mapping (a
dashboard charting the wrong scale is worse than no dashboard) and the control
coverage cardinality (bounded by frameworks x capabilities, NOT by workloads —
that is the design decision that keeps this usable at 600 workloads).
"""
from resops.assurance.metrics import control_coverage, render_metrics

SUMMARY = {"workloads": [
    {"name": "payments-api", "state": "VALIDATED", "gate": "PROMOTE",
     "env": "prod", "owner": "payments", "criticality": "critical",
     "blocked_stage": None, "attestation_age_days": 2.0},
    {"name": "checkout-api", "state": "RECOVERABLE", "gate": "HOLD",
     "env": "prod", "owner": "payments", "criticality": "critical",
     "blocked_stage": "Scan", "attestation_age_days": 0.0},
    {"name": "legacy-batch", "state": "UNDISCOVERED", "gate": "HOLD",
     "env": "prod", "owner": "finance", "criticality": "standard",
     "blocked_stage": "Discover", "attestation_age_days": None},
]}


def _bundle(*functions):
    return {"functions": [
        {"function": name, "outcome": outcome,
         "controls": [{"id": cap, "references": {"dora": ref}}]}
        for name, outcome, cap, ref in functions]}


# --------------------------------------------------------------------------- #
# The rung must chart on the ladder's own scale.
# --------------------------------------------------------------------------- #
def test_rung_uses_the_ladders_own_ranks():
    out = render_metrics(SUMMARY, [])
    assert 'resops_rung{workload="payments-api",env="prod",owner="payments",' \
           'criticality="critical"} 6' in out
    assert 'workload="legacy-batch"' in out and "} 0" in out


def test_an_unknown_state_is_omitted_not_guessed():
    # A missing series is honest. A wrong number on a dashboard is not.
    out = render_metrics({"workloads": [{"name": "x", "state": "BANANA"}]}, [])
    assert "resops_rung{" not in out


def test_promotable_is_binary_and_override_counts_as_shippable():
    out = render_metrics({"workloads": [
        {"name": "a", "state": "VALIDATED", "gate": "PROMOTE"},
        {"name": "b", "state": "VALIDATED", "gate": "OVERRIDE"},
        {"name": "c", "state": "PROTECTED", "gate": "HOLD"}]}, [])
    assert 'resops_promotable{workload="a"} 1' in out
    assert 'resops_promotable{workload="b"} 1' in out
    assert 'resops_promotable{workload="c"} 0' in out


# --------------------------------------------------------------------------- #
# Absent data must stay absent — never rendered as zero or "".
# --------------------------------------------------------------------------- #
def test_missing_attestation_age_emits_no_series():
    # legacy-batch has never been attested. Zero days would read as "verified
    # today", which is the exact lie this project spent a day removing.
    out = render_metrics(SUMMARY, [])
    assert 'attestation_age_days{workload="legacy-batch"}' not in out
    assert 'attestation_age_days{workload="payments-api"} 2.0' in out


def test_empty_labels_are_dropped_not_rendered_blank():
    out = render_metrics(SUMMARY, [])
    assert 'blocked_stage=""' not in out
    assert 'blocked_stage="Scan"' in out


# --------------------------------------------------------------------------- #
# Control coverage — a count, and its cardinality must not track workloads.
# --------------------------------------------------------------------------- #
def test_control_coverage_counts_workloads_per_outcome():
    bundles = [
        _bundle(("validate", "PASS", "CAP-RESTORE-TESTED", "Art. 11/12")),
        _bundle(("validate", "GAP", "CAP-RESTORE-TESTED", "Art. 11/12")),
        _bundle(("validate", "GAP", "CAP-RESTORE-TESTED", "Art. 11/12")),
    ]
    tally = control_coverage(bundles)
    assert tally[("dora", "Art. 11/12", "CAP-RESTORE-TESTED", "PASS")] == 1
    assert tally[("dora", "Art. 11/12", "CAP-RESTORE-TESTED", "GAP")] == 2


def test_cardinality_is_bounded_by_controls_not_workloads():
    # THE design decision. Ten workloads over the same control produce ONE series,
    # not ten. This is what keeps the exposition sane at 600 workloads.
    one = control_coverage([_bundle(("validate", "PASS", "CAP-RESTORE-TESTED", "Art. 12"))])
    many = control_coverage([_bundle(("validate", "PASS", "CAP-RESTORE-TESTED", "Art. 12"))] * 10)
    assert len(one) == len(many) == 1
    assert many[("dora", "Art. 12", "CAP-RESTORE-TESTED", "PASS")] == 10


def test_coverage_is_absent_when_no_frameworks_are_configured():
    # Frameworks are opt-in per config. No packs declared, no claims made.
    assert control_coverage([{"functions": [{"function": "validate", "outcome": "PASS"}]}]) == {}


def test_the_indicative_disclaimer_rides_with_the_metric():
    # A dashboard makes a mapping look more official than a markdown note does.
    out = render_metrics(SUMMARY, [_bundle(("validate", "PASS", "CAP-RESTORE-TESTED", "Art. 12"))])
    assert "INDICATIVE" in out


# --------------------------------------------------------------------------- #
# Exposition format — label values must survive the awkward characters.
# --------------------------------------------------------------------------- #
def test_quotes_and_backslashes_in_labels_are_escaped():
    bundles = [_bundle(("validate", "PASS", "CAP-X", 'Art. 12 "quoted" \\ back'))]
    out = render_metrics({"workloads": []}, bundles)
    assert '\\"quoted\\"' in out and "\\\\ back" in out


def test_every_metric_carries_help_and_type():
    out = render_metrics(SUMMARY, [])
    for name in ("rung", "promotable", "attestation_age_days",
                 "workload_info", "workloads_total"):
        assert f"# HELP resops_{name} " in out
        assert f"# TYPE resops_{name} gauge" in out
