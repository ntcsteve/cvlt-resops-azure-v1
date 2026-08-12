"""The guide's live half, held to the same rule as a recovery point.

WHY THIS EXISTS. `test_workshop_guide.py` pins the OFFLINE steps: the commands
must appear in WORKSHOP.md and still produce what it promises. The LIVE half has
never had any binding at all, so when commit d9d01a6 changed what `op restore`
prints, the guide drifted for NINE DAYS and only a manual walk caught it. That
walk has happened once in seven sessions, so "someone will notice" is not a
control.

THE PRINCIPLE IS ALREADY IN THIS REPO, in a different domain:

    RECOVERY   an attestation is a claim about ONE recovery point.
               It must be NEWER than the point it vouches for.  (05d4a1c)

    THE GUIDE  a walk is a claim about ONE state of the code.
               It must be NEWER than the code it vouches for.   (here)

So this does not verify the guide is CORRECT. It verifies that nobody is
claiming verification they no longer have, which is exactly the distinction the
Scan rung draws between "attested clean" and "nothing has looked". Absence of a
walk is not a pass.

WHAT IT DELIBERATELY DOES NOT DO. It does not diff guide text against captured
logs. Those logs carry the subscription GUID so they cannot be committed, and
most promised strings are shell-generated or interpolated and would never match.
Half a mechanism with a maintenance tail is worse than an honest date.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RECORD = Path(__file__).parent / "workshop_walk.json"

# The files whose OUTPUT the guide's live boxes quote. A change to any of them
# can silently invalidate a "✓ YOU SHOULD SEE" box. Kept deliberately narrow:
# a trigger that fires on everything gets deleted by the third false alarm.
LIVE_SURFACE = (
    "resops/operator",                        # the commands the guide runs
    "resops/render.py",                       # the ladder as it is drawn
    "resops/state.py",                        # the per-rung reasons
    "resops/gate.py",                         # PROMOTE / HOLD wording
    "infra/modules/azure-vm/cloud-init.yaml",  # verify.sh, source of the FAIL line
)


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def _commit_time(rev: str) -> int:
    return int(_git("show", "-s", "--format=%ct", rev))


def test_the_record_is_well_formed():
    """A record nobody can parse is not a record."""
    rec = json.loads(RECORD.read_text())
    assert rec["walked_at"] and rec["walked_commit"]
    assert rec["verified"], "a walk that verified nothing is not a walk"
    # `not_verified` may be empty one day, but the key must exist: silence about
    # what was NOT checked is how a partial walk reads as a complete one.
    assert "not_verified" in rec


def test_the_walk_is_newer_than_the_code_it_vouches_for():
    """THE GUARD. Fails when the live surface has moved since the last walk.

    When this fires you have two honest options: re-walk the affected boxes, or
    review the change, confirm it touches no asserted output, and move
    walked_commit forward WITH a note. What you must not do is bump the SHA to
    get a green tick, which is the documentation equivalent of a scan that
    examined nothing."""
    rec = json.loads(RECORD.read_text())
    walked = rec["walked_commit"]
    walked_ts = _commit_time(walked)

    newest = _git("log", "-1", "--format=%H %ct", "--", *LIVE_SURFACE)
    if not newest:                      # nothing on the live surface yet
        return
    sha, ts = newest.split()

    if int(ts) > walked_ts:
        changed = _git("log", "--oneline", f"{walked}..HEAD", "--", *LIVE_SURFACE)
        raise AssertionError(
            f"WORKSHOP.md's live half was last walked at {walked} "
            f"({rec['walked_at']}), but the code its boxes quote has changed "
            f"since:\n\n{changed}\n\n"
            f"Re-walk the affected boxes, or review those commits and move "
            f"walked_commit forward in tests/workshop_walk.json with a note "
            f"saying why they do not affect asserted output.")
