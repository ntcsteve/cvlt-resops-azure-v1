"""Does a non-zero verdict actually leave the process non-zero?

WHY THIS FILE EXISTS. `op.main()` calls `CMDS[cmd](run_dir)` and DISCARDS the
return value. That is correct for most commands, which raise SystemExit on
failure and return nothing (or return a domain value like a group id, which is
not an exit code at all). It was wrong for exactly one: `restore` returned the
restore drill's four-way verdict

    0  restored, healthy, and verify.sh said clean
    1  the drill could not run to a verdict
    2  restored, but the copy came back unhealthy
    3  restored and healthy, but NOT clean

straight into a caller that threw it away. Run as a module the drill honours its
own codes (`sys.exit(main())`); routed through `op` all four exited 0. When the
drill failed on the OS-disk bug on 2026-08-12, `op restore` exited 0 and the only
reason anyone noticed was a human reading the printed verdict.

Same shape as TIMEOUT-as-a-status (see test_job_status.py): a meaningful value
handed to somebody who does not look at it. The fix is the idiom `gate` and
`_cli_threatscan` already use — when a command's exit code IS the verdict, the
command exits.

These tests never touch Azure or Commvault. They replace `restore` with a stub
that returns a code, which is the whole surface under test.
"""
import pytest

from resops.operator import op


def _cli(code, monkeypatch):
    """Run `op restore`'s CLI wrapper against a drill that returned `code`."""
    monkeypatch.setattr(op, "restore", lambda run_dir: code)
    op._cli_restore("infra/workloads")


def test_a_clean_drill_exits_zero(monkeypatch):
    """The pass path must stay silent and fall through. If this starts raising,
    every green climb turns into a failure."""
    _cli(op._DRILL_OK, monkeypatch)


@pytest.mark.parametrize("code", [op._DRILL_COULD_NOT_RUN,
                                  op._DRILL_UNHEALTHY,
                                  op._DRILL_DIRTY])
def test_EVERY_NON_ZERO_VERDICT_LEAVES_THE_PROCESS_NON_ZERO(code, monkeypatch):
    """THE REGRESSION GUARD, and the reason this module exists.

    All three failure verdicts are different situations, but they agree on one
    thing: nothing was proven, so the command must not report success."""
    with pytest.raises(SystemExit) as exc:
        _cli(code, monkeypatch)
    # SystemExit carrying a string exits 1 and prints it. What must never happen
    # is code 0 or None.
    assert exc.value.code not in (0, None)


@pytest.mark.parametrize("code", [op._DRILL_COULD_NOT_RUN,
                                  op._DRILL_UNHEALTHY,
                                  op._DRILL_DIRTY])
def test_each_failure_says_which_one_it_was(code, monkeypatch):
    """At 2am "the drill failed" is not actionable. "could not run" means fix the
    environment and re-run; "not clean" means the drill worked and the backup is
    the problem. Opposite next actions, so they must not share a message."""
    with pytest.raises(SystemExit) as exc:
        _cli(code, monkeypatch)
    assert op._DRILL_VERDICT[code] in str(exc.value.code)


def test_the_three_failure_messages_are_distinct():
    """Belt and braces on the same idea: no two verdicts may collapse into the
    same words, or the distinction above is decorative."""
    msgs = list(op._DRILL_VERDICT.values())
    assert len(set(msgs)) == len(msgs)


def test_climb_stops_when_the_drill_does_not_pass(monkeypatch):
    """`climb` calls `restore` directly, not through the CLI wrapper, so it needs
    its own check — and this is where the original bug did the real damage: the
    climb carried on to `status` and rendered a ladder built on a drill that
    never reached a verdict."""
    monkeypatch.setattr(op.preflight, "run", lambda run_dir: None)
    monkeypatch.setattr(op, "protect", lambda run_dir: 1234)
    monkeypatch.setattr(op, "backup", lambda run_dir, gid=None: "Completed")
    monkeypatch.setattr(op, "restore", lambda run_dir: op._DRILL_DIRTY)
    monkeypatch.setattr(op, "status", lambda run_dir: pytest.fail(
        "climb reached status after a failed drill — the bug is back"))
    with pytest.raises(SystemExit):
        op.climb("infra/workloads")


def test_the_guest_paths_the_two_scripts_use_are_the_same_paths():
    """`incident` dirties DATA and parks originals in STASH; `remediate` cleans
    DATA and restores from STASH. They live in separate heredocs 70 lines apart,
    so if one is edited and the other is not, remediate tidies a directory
    incident never touched and reports success. This pins them together."""
    scripts = {name: op._guest_paths(getattr(op, name))
               for name in ("_INCIDENT_SCRIPT", "_REMEDIATE_SCRIPT")}
    for name, body in scripts.items():
        assert f"DATA={op._DATA_DIR}" in body, name
        assert f"STASH={op._STASH_DIR}" in body, name
        assert "{data_dir}" not in body and "{stash_dir}" not in body, \
            f"{name} would reach the guest with an unfilled placeholder"


# --------------------------------------------------------------------------- #
# Now that a TIMEOUT hard-fails the drill, the timeout VALUE became load-bearing.
# It used to be harmless: poll_job gave up at 540s, returned "TIMEOUT", and the
# drill sailed on and exited 0. With that hole closed, a too-short timeout no
# longer hides — it manufactures a failure, and a team that sees green-on-retry
# learns to re-run things until they pass. That is worse than the original bug.
#
# These pin the RELATIONSHIP, not the number. Tuning 900 up is fine; making the
# restore wait less patiently than a backup is not.
# --------------------------------------------------------------------------- #
def test_the_restore_drill_waits_at_least_as_long_as_a_backup():
    """A restore queues behind a media agent slot exactly like a backup does. If
    it gives up sooner, the drill fails on a wait the backup lane would have sat
    through, and the failure is ours, not the tenant's. It was 540s against the
    backup lane's 600s — the LOWEST timeout in the codebase, on the operation that
    waits longest."""
    import inspect

    from resops.operator.commvault import poll_job
    from resops.operator.drills.run_restore import RESTORE_POLL_TIMEOUT

    backup_default = inspect.signature(poll_job).parameters["timeout"].default
    assert RESTORE_POLL_TIMEOUT >= backup_default, (
        f"the restore drill gives up at {RESTORE_POLL_TIMEOUT}s while a backup is "
        f"allowed {backup_default}s, so the drill will fail on waits the backup "
        f"lane tolerates")


def test_the_restore_drill_waits_out_the_delay_it_warns_you_about():
    """poll_job prints "waiting for a media agent slot — typically 5-15 min" on the
    first Waiting tick. A timeout inside the window we tell the operator to expect
    is the tool contradicting its own advice, which at 2am costs more than the
    wait would have."""
    from resops.operator.drills.run_restore import RESTORE_POLL_TIMEOUT
    assert RESTORE_POLL_TIMEOUT >= 15 * 60
