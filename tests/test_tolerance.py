"""The ratchet – declared, expiring enforcement tolerance.

These tests exist to pin the ONE property that separates a ratchet from a
bypass: a tolerated workload's own verdict must never change. If someone later
"simplifies" this by making gate() return PROMOTE for a tolerated workload, the
gap disappears from the screen, the bundle and the report, and the feature
becomes the thing it was built to avoid. test_tolerated_workload_still_holds is
the guard on that.
"""
import json

import pytest
import yaml

from resops.__main__ import _resolve_tolerance, main
from resops.assurance.metrics import render_metrics
from resops.gate import tolerated

FUTURE, PAST = "2099-01-01", "2020-01-01"


# --------------------------------------------------------------------------- #
# The pure policy function.
# --------------------------------------------------------------------------- #
def test_tolerance_is_live_before_the_date_and_dead_on_it():
    assert tolerated("2026-10-01", "2026-09-30") is True
    assert tolerated("2026-10-01", "2026-10-01") is False   # the day it bites
    assert tolerated("2026-10-01", "2026-10-02") is False


def test_a_malformed_date_raises_rather_than_tolerating_forever():
    # Failing OPEN here would silently exempt a workload for good, which is the
    # exact failure mode the date was chosen to prevent.
    with pytest.raises(ValueError):
        tolerated("not-a-date", "2026-10-01")
    with pytest.raises(ValueError):
        tolerated("2026-13-01", "2026-10-01")


# --------------------------------------------------------------------------- #
# Resolution at the I/O edge.
# --------------------------------------------------------------------------- #
def test_undeclared_means_enforced():
    w = {"name": "a"}
    assert _resolve_tolerance(w, "2026-10-01") == ""
    assert w["tolerated"] is False


def test_yaml_date_objects_and_strings_both_resolve():
    import datetime
    for declared in (datetime.date(2099, 1, 1), "2099-01-01"):
        w = {"name": "a", "enforce_from": declared}
        assert _resolve_tolerance(w, "2026-10-01") == ""
        assert w["tolerated"] is True


def test_a_typo_returns_the_fix_not_a_crash():
    w = {"name": "reporting-db", "enforce_from": "next quarter"}
    err = _resolve_tolerance(w, "2026-10-01")
    assert "reporting-db" in err and "YYYY-MM-DD" in err


# --------------------------------------------------------------------------- #
# End to end: what the ratchet actually changes, and what it must not.
# --------------------------------------------------------------------------- #
def _estate(tmp_path, enforce_from=None):
    """Two workloads: one VALIDATED, one blocked at Detect. Optionally tolerate
    the blocked one. Bars are wide open so the fixtures' fixed timestamps can
    never flip a verdict (same reason config/estate.yaml declares them)."""
    blocked = {"name": "reporting-db", "tier": "tier2",
               "fixture": "config/demo/backup-failed.json"}
    if enforce_from:
        blocked["enforce_from"] = enforce_from
        blocked["tolerance_reason"] = "backup policy rebuild in flight"
    config = {
        "evidence_dir": str(tmp_path / "evidence"),
        "gate": {"frameworks": ["dora"],
                 "recovery_proof_max_age_days": 36500,
                 "attestation_max_age_days": 36500,
                 "rpo_target_hours": 999999, "rto_target_minutes": 999999},
        "workloads": [
            {"name": "payments-api", "tier": "tier1",
             "fixture": "config/demo/validated.json"},
            blocked,
        ],
    }
    path = tmp_path / "estate.yaml"
    path.write_text(yaml.safe_dump(config))
    return path, tmp_path / "evidence" / "summary.json"


def test_without_a_tolerance_one_hold_holds_the_estate(tmp_path):
    config, _ = _estate(tmp_path)
    assert main(["gate", str(config)]) == 1


def test_a_live_tolerance_unblocks_the_aggregate(tmp_path):
    config, summary_path = _estate(tmp_path, FUTURE)
    assert main(["gate", str(config)]) == 0
    aggregate = json.loads(summary_path.read_text())["aggregate"]
    assert aggregate["decision"] == "PROMOTE"
    # The gap is counted, not dropped. This list is the number that must go down.
    assert aggregate["tolerated"] == ["reporting-db"]


def test_tolerated_workload_still_holds(tmp_path):
    """THE GUARD. Tolerating a workload defers enforcement, never the verdict."""
    config, summary_path = _estate(tmp_path, FUTURE)
    main(["gate", str(config)])
    workload = [w for w in json.loads(summary_path.read_text())["workloads"]
                if w["name"] == "reporting-db"][0]
    assert workload["gate"] == "HOLD"           # unchanged
    assert workload["blocked_stage"] == "Detect"  # still named
    assert workload["tolerated"] is True         # and declared


def test_an_expired_tolerance_enforces_itself(tmp_path):
    """No action required for the ratchet to bite. That is the point of a date."""
    config, summary_path = _estate(tmp_path, PAST)
    assert main(["gate", str(config)]) == 1
    aggregate = json.loads(summary_path.read_text())["aggregate"]
    assert aggregate["decision"] == "HOLD"
    assert aggregate["tolerated"] == []


def test_the_tolerance_reaches_the_evidence_bundle(tmp_path):
    config, _ = _estate(tmp_path, FUTURE)
    main(["gate", str(config)])
    bundle = json.loads((tmp_path / "evidence" / "reporting-db" / "bundle.json").read_text())
    assert bundle["gate"]["decision"] == "HOLD"
    assert bundle["gate"]["tolerance"] == {
        "enforce_from": FUTURE, "active": True,
        "reason": "backup policy rebuild in flight"}
    report = (tmp_path / "evidence" / "reporting-db" / "report.md").read_text()
    assert "Enforcement tolerance" in report and FUTURE in report


def test_a_bad_date_stops_the_run_before_any_read(tmp_path):
    config, _ = _estate(tmp_path, "whenever")
    assert main(["gate", str(config)]) == 2      # CONFIG_ERROR, not a HOLD


# --------------------------------------------------------------------------- #
# The published number.
# --------------------------------------------------------------------------- #
def test_metrics_publish_tolerated_for_every_workload():
    """0 is emitted too: a series that only appears when someone opts out cannot
    be trended, and trending it down is the entire purpose."""
    out = render_metrics({"workloads": [
        {"name": "payments-api", "state": "VALIDATED", "gate": "PROMOTE"},
        {"name": "reporting-db", "state": "PROTECTED", "gate": "HOLD",
         "tolerated": True, "enforce_from": "2027-01-01"},
    ]}, [])
    assert 'resops_tolerated{workload="payments-api"} 0' in out
    assert 'resops_tolerated{workload="reporting-db"} 1' in out
    assert 'enforce_from="2027-01-01"' in out
    # No tolerance declared → no label, so an untouched estate gains no cardinality.
    assert 'workload="payments-api",state="VALIDATED",gate="PROMOTE"} 1' in out
