"""Was the job a success? – the one question, asked in one place.

WHY THIS FILE EXISTS. `poll_job` returns a job's terminal status, and "TIMEOUT"
when it gave up waiting. Those are not the same kind of thing: a status is an
observed outcome, TIMEOUT is the ABSENCE of one, and both came back through the
same return value. So every caller had to remember to special-case it by hand.
One did – the restore drill, with `status == "TIMEOUT" or "Failed" in status or
"Killed" in status` – and one did not: `op backup` printed "backup TIMEOUT",
returned it, and exited 0, so `climb` carried on and restored an OLDER recovery
point. Live on 2026-08-12 when the tenant failed a workload over to a different
media agent mid-session and the backup never started.

The ladder still caught it at Detect, which reads the group's own lastBackup
status, so it was never a false promotion – but ten minutes went on proving
something about the wrong recovery point, and the output read as though it had
worked. That is the same shape as taking disks[0], and as reading an absent
anomaly as clean: a value that does not mean what its channel implies.

These tests are cheap. The last one is the one that matters.
"""
from resops.operator.commvault import TERMINAL, succeeded


def test_completed_is_success():
    assert succeeded("Completed") is True


def test_completed_with_warnings_or_errors_still_counts():
    """The job produced data, so it succeeded AS A JOB. Whether the data is any
    good is judged twice elsewhere and independently: the Detect rung reads the
    group's lastBackup status and failureReason, and verify.sh opens the restored
    copy and reads it. This function judges the job and nothing else – widening
    it to mean "and the data is fine" is how an attester starts lying."""
    assert succeeded("Completed w/ one or more warnings") is True
    assert succeeded("Completed w/ one or more errors") is True


def test_failed_and_killed_are_not_success():
    assert succeeded("Failed") is False
    assert succeeded("Killed") is False


def test_no_status_at_all_is_not_success():
    """An empty or missing status is the absence of an answer, and absence never
    reads as a pass anywhere in this codebase."""
    assert succeeded("") is False
    assert succeeded(None) is False


def test_TIMEOUT_IS_NOT_SUCCESS():
    """THE REGRESSION GUARD, and the reason this module exists.

    TIMEOUT means poll_job stopped waiting. The job may still be running. We
    cannot claim an outcome we never observed. If someone later "simplifies"
    poll_job to return something status-shaped on timeout, this fails first."""
    assert succeeded("TIMEOUT") is False


def test_timeout_is_deliberately_not_a_terminal_state():
    """Belt and braces on the same idea from the other direction: TIMEOUT must
    never be added to TERMINAL, because that would make poll_job return early
    and report a result it did not see."""
    assert "TIMEOUT" not in TERMINAL
    assert TERMINAL == ("Completed", "Failed", "Killed")
