"""The verify.sh output contract (VERIFY.md), pinned.

Every rule here fails SILENTLY when broken — a truncated detail, or worse, an
unattested point reading as clean. Those are the two ways an attester lies, and
this project already learned what a lying attester costs. If a change makes one
of these tests fail, the change is wrong until VERIFY.md says otherwise.
"""
from resops.operator.drills.run_restore import VERIFY_SCRIPT, parse_verdict


def test_ok_line_attests_clean_and_carries_the_detail():
    clean, detail = parse_verdict("OK: code intact, baseline present, 3 records")
    assert clean is True
    assert detail == "code intact, baseline present, 3 records"


def test_fail_line_attests_dirty_and_carries_the_detail():
    clean, detail = parse_verdict("FAIL: 14 encrypted (.locked) files present")
    assert clean is False
    assert detail == "14 encrypted (.locked) files present"


def test_the_verdict_is_found_among_other_output():
    clean, detail = parse_verdict(
        "checking code…\nchecking records…\nOK: all good\n")
    assert (clean, detail) == (True, "all good")


def test_silence_is_unattested_never_clean():
    """The rule the whole Scan rung rests on: no result is not a pass."""
    for stdout in ("", "some noise\nmore noise", "ok: lowercase is not the contract"):
        clean, detail = parse_verdict(stdout)
        assert clean is None, stdout
        assert "no verdict" in detail


def test_a_missing_script_says_so_plainly():
    clean, detail = parse_verdict("NO VERIFY SCRIPT")
    assert clean is None
    assert VERIFY_SCRIPT in detail and "no attester" in detail


def test_only_the_first_line_is_read():
    """WHY THIS IS PINNED: parsing stops at the first match, so a verdict message
    wrapped over two lines loses its tail — silently, into the attestation, the
    gate reason and the evidence bundle. That is a real bug this repo shipped.
    The contract is one line per message; this test is what makes that true
    rather than merely documented."""
    clean, detail = parse_verdict("FAIL: BASELINE marker missing\nno known-good state")
    assert clean is False
    assert detail == "BASELINE marker missing"          # the tail is gone, by design
    # And a later verdict can never override an earlier one.
    assert parse_verdict("FAIL: dirty\nOK: clean")[0] is False


def test_a_crash_after_a_clean_verdict_still_reads_clean():
    """An honest limit, pinned so nobody discovers it in an incident: print the
    verdict LAST. This parser cannot know the script died after announcing OK."""
    assert parse_verdict("OK: all good\nsegfault")[0] is True
