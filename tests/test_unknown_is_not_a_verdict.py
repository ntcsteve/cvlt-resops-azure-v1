""""I could not check" must never be reported as "I checked, and it is bad".

WHY THIS FILE EXISTS. On 2026-08-13 the same mistake was found in three places,
all in the write lane, all producing a confident wrong answer from a missing one:

  run_restore  `return 0 if clean else 3` collapsed None into False, so a guest
               agent that never answered exited 3 ("this recovery point is poison,
               do not retry") while the printed verdict said UNATTESTED. Two
               contradictory statements in one output block.

  _azure       az_json() returns None both when a resource is absent and when the
               `az` call FAILED. teardown read that as absence, announced
               "nothing to tear down", returned success, and left a VM, a NIC and
               a disk running and billing.

  state.Scan   `if not attestation.get("clean")` sent None and False down the same
               branch, so a drill that reached no verdict was reported as a
               recovery point that FAILED verification. Both HOLD, correctly — but
               one says go hunt a compromise and the other says re-run the drill.

The read lane has always failed closed. These are the write lane not doing so.
None of these tests need Azure, Commvault, or a clock.
"""
import subprocess

import pytest

from resops.operator._azure import az_json_checked
from resops.operator.drills.run_restore import verdict_code
from resops.state import State, classify

from test_state import _full_reads, _scan


# --------------------------------------------------------------------------- #
# 1. The drill's four-way contract. THREE verdicts feed it, not two.
# --------------------------------------------------------------------------- #
def test_a_clean_copy_is_zero():
    assert verdict_code(healthy=True, clean=True) == 0


def test_a_dirty_copy_is_three():
    assert verdict_code(healthy=True, clean=False) == 3


def test_NO_VERDICT_IS_NOT_A_DIRTY_VERDICT():
    """The bug. `clean is None` means the attester never reached an answer.

    3 tells an operator the recovery point is poison and retrying is pointless.
    1 tells them nothing was proven and to run it again. Getting this wrong sends
    someone hunting a compromise that was never detected.
    """
    assert verdict_code(healthy=True, clean=None) == 1


def test_an_unhealthy_copy_outranks_everything():
    """A copy that did not come back healthy is 2 whatever the attester said —
    including when it said nothing."""
    assert verdict_code(healthy=False, clean=True) == 2
    assert verdict_code(healthy=False, clean=False) == 2
    assert verdict_code(healthy=False, clean=None) == 2


def test_the_four_codes_are_all_reachable():
    """A contract with an unreachable slot is a contract with a missing case.
    Slot 1 was unreachable until 2026-08-13."""
    reached = {verdict_code(h, c)
               for h in (True, False) for c in (True, False, None)}
    assert reached == {0, 1, 2, 3}


# --------------------------------------------------------------------------- #
# 2. az_json_checked — absence and failure must not look alike.
# --------------------------------------------------------------------------- #
class _Result:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def _az(monkeypatch, result):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: result)


def test_a_real_answer_comes_back_parsed(monkeypatch):
    _az(monkeypatch, _Result(0, '{"name": "vm01"}'))
    assert az_json_checked("vm", "show")["name"] == "vm01"


def test_a_genuinely_absent_resource_is_none(monkeypatch):
    """az exits non-zero for a missing resource, so the REASON is what separates
    'not there' from 'could not ask'. This is the only signal az gives."""
    _az(monkeypatch, _Result(3, "", "ERROR: (ResourceNotFound) VM 'x' not found"))
    assert az_json_checked("vm", "show") is None


def test_A_FAILED_LOOKUP_RAISES_INSTEAD_OF_LOOKING_EMPTY(monkeypatch):
    """The bug. Throttling, an expired login, a network blip — none of them mean
    the resource is gone, and the caller that turns None into "nothing to tear
    down" will happily report a clean sweep over a VM that is still billing."""
    _az(monkeypatch, _Result(1, "", "ERROR: AADSTS700082 refresh token expired"))
    with pytest.raises(SystemExit) as exc:
        az_json_checked("vm", "show", "-n", "vm01")
    assert "cannot tell whether it exists" in str(exc.value)


def test_an_empty_success_is_still_absence(monkeypatch):
    """az answered, and the answer was nothing. That IS absence."""
    _az(monkeypatch, _Result(0, "   "))
    assert az_json_checked("vm", "list") is None


# --------------------------------------------------------------------------- #
# 3. The Scan rung — UNATTESTED and FAILED need different fixes.
# --------------------------------------------------------------------------- #
def test_an_attestation_with_no_verdict_says_unattested_not_failed():
    """The bug. Both HOLD at Scan, which is correct — this rung fails closed
    either way. What differs is the instruction the operator is handed."""
    ladder = classify(_full_reads(
        attestation=_scan(clean=None, source="restore-verify",
                          detail="could not run the verify script")))
    assert ladder.state is State.RECOVERABLE
    assert ladder.blocked_stage == "Scan"
    assert "UNATTESTED" in ladder.reason
    assert "re-run the restore drill" in ladder.reason
    assert "failed" not in ladder.reason.lower()


def test_a_real_failure_still_says_failed():
    """The other side of the same branch must not regress: when the attester DID
    look and DID find something, the reason must still accuse the recovery point."""
    ladder = classify(_full_reads(
        attestation=_scan(clean=False, source="restore-verify",
                          detail="14 encrypted (.locked) files present")))
    assert ladder.state is State.RECOVERABLE
    assert ladder.blocked_stage == "Scan"
    assert "failed restore-verify" in ladder.reason
    assert "14 encrypted" in ladder.reason


def test_both_still_hold_so_the_rung_never_got_weaker():
    """The fix changes the MESSAGE, never the verdict. If either of these ever
    reaches VALIDATED, the rung has been broken in the way that matters most."""
    for clean in (None, False):
        ladder = classify(_full_reads(attestation=_scan(clean=clean)))
        assert ladder.state is not State.VALIDATED
