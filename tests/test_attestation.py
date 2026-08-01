"""The attestation lane — reading it, and dating it.

Two small functions with an outsized ability to lie. The reader decides whether
anyone has vouched for a recovery point; the clock decides whether that vouching
is still worth anything. Both have branches where the wrong answer is SILENT —
a pass where there should be a block — which is the failure this project spent
2026-08-01 removing. So each branch is pinned.
"""
import json
import time

from resops.reads import _attestation_age_days
from resops.state import _restore_verify_attestation


# --------------------------------------------------------------------------- #
# Reading it — five ways to have no attestation, and none of them is a pass.
# --------------------------------------------------------------------------- #
def test_no_declared_file_means_nobody_attested():
    assert _restore_verify_attestation(None) == (None, "")
    assert _restore_verify_attestation("") == (None, "")


def test_declared_but_missing_file_is_unattested_not_an_error():
    # A workload configured for restore-verify whose drill has never run. That is
    # a gap to report, not a read failure to alarm on — the Scan rung blocks
    # either way, but blocked_by_error must stay False so it reads as a real gap.
    attestation, error = _restore_verify_attestation("/nonexistent/never-ran.json")
    assert attestation is None
    assert error == ""


def test_a_clean_attestation_is_returned_whole(tmp_path):
    p = tmp_path / "a.json"
    p.write_text(json.dumps({"source": "restore-verify", "clean": True,
                             "detail": "3 customer records", "at": 1785000000}))
    attestation, error = _restore_verify_attestation(str(p))
    assert error == ""
    assert attestation["clean"] is True
    assert attestation["source"] == "restore-verify"


def test_a_failed_attestation_is_also_returned(tmp_path):
    # A negative is still an attestation — somebody looked and did not like it.
    p = tmp_path / "a.json"
    p.write_text(json.dumps({"source": "restore-verify", "clean": False,
                             "detail": "14 encrypted (.locked) files present"}))
    attestation, _ = _restore_verify_attestation(str(p))
    assert attestation["clean"] is False


def test_clean_null_means_the_drill_could_not_verify(tmp_path):
    # THE subtle one. The drill ran, restored, and could not run verify.sh — no
    # guest agent, no script, whatever. That is not "clean" and it is not a
    # failure either; it is an absence, and absence must never clear the rung.
    p = tmp_path / "a.json"
    p.write_text(json.dumps({"source": "restore-verify", "clean": None,
                             "detail": "guest agent unreachable"}))
    assert _restore_verify_attestation(str(p)) == (None, "")


def test_unreadable_file_reports_an_error_rather_than_passing(tmp_path):
    p = tmp_path / "a.json"
    p.write_text("{ this is not json")
    attestation, error = _restore_verify_attestation(str(p))
    assert attestation is None
    assert "unreadable" in error


# --------------------------------------------------------------------------- #
# Dating it — an attestation with no date is half a claim.
# --------------------------------------------------------------------------- #
def test_no_attestation_has_no_age():
    assert _attestation_age_days(None) is None


def test_an_undated_attestation_has_no_age():
    # Undated means the gate cannot enforce freshness on it. Better to return
    # None (bar unenforced, age visible as absent) than to invent a number.
    assert _attestation_age_days({"source": "restore-verify", "clean": True}) is None


def test_age_is_measured_in_days():
    two_days = {"at": int(time.time()) - 2 * 86400}
    assert _attestation_age_days(two_days) == 2.0


def test_a_fresh_attestation_is_near_zero_not_absent():
    # 0.0 and None mean very different things downstream: 0.0 is "verified just
    # now", None is "nobody ever did". They must not collapse into each other.
    assert _attestation_age_days({"at": int(time.time())}) == 0.0
