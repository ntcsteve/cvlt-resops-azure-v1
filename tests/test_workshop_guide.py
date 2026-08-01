"""WORKSHOP.md is executable documentation, and this is what keeps it true.

WHY THIS EXISTS. The first draft of M1 pasted the README's estate block into a
"you should see" box. The README block is an illustration — the real tool prints
a ▸ header line, a bar line and a reason line per workload, and no summary
column. In a room, twenty people would have compared their screen to the guide,
found it different, and stopped trusting the guide on page one.

A workshop guide that lives in the repo only beats a hosted one if it is
VERIFIED here. Otherwise it is a website with worse hosting.

Two directions of drift, both caught:

  the TOOL changes   → `must_contain` stops appearing in the output
  the GUIDE changes  → `command` is no longer found verbatim in WORKSHOP.md

Only OFFLINE steps run here. Live steps need a tenant and are the facilitator's
rehearsal, not CI's job. Every offline step in the guide belongs in this list.
"""
import re
import subprocess
import sys

from resops.__main__ import ROOT

GUIDE = ROOT / "WORKSHOP.md"
ANSI = re.compile(r"\x1b\[[0-9;]*m")

OFFLINE_STEPS = [
    {
        "module": "M1.1 — see the gap",
        "command": "python3 -m resops gate config/estate.yaml",
        "exit_code": 1,
        "must_contain": [
            "▸ payments-api",
            "●●●●●●  VALIDATED",
            "●●●●✗·  RECOVERABLE",
            "blocked at Scan",
            "recovery point failed restore-verify",
            "AGGREGATE  HOLD",
        ],
    },
    {
        "module": "M6.4 — four recovery points",
        "command": "python3 -m resops gate config/incident.yaml",
        "exit_code": 1,
        "must_contain": [
            "▸ D-7-hours-ago",
            "PROMOTE",
            "recovery point is UNATTESTED",
            "rpo 144.0h > target 8h",
            "attestation stale (400.0d > 30d)",
        ],
    },
]


def _run(command: str):
    argv = command.replace("python3", sys.executable, 1).split()
    proc = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True)
    return proc.returncode, ANSI.sub("", proc.stdout + proc.stderr)


def test_every_offline_command_is_actually_in_the_guide():
    """Catches the guide being edited away from what CI verifies."""
    text = GUIDE.read_text()
    for step in OFFLINE_STEPS:
        assert step["command"] in text, (
            f"{step['module']}: '{step['command']}' is verified here but no longer "
            f"appears in WORKSHOP.md")


def test_every_offline_command_still_produces_what_the_guide_promises():
    """Catches the tool being changed away from what the guide shows a room."""
    for step in OFFLINE_STEPS:
        code, output = _run(step["command"])
        assert code == step["exit_code"], (
            f"{step['module']}: `{step['command']}` exited {code}, "
            f"guide says {step['exit_code']}")
        for expected in step["must_contain"]:
            assert expected in output, (
                f"{step['module']}: the guide promises {expected!r} and the tool "
                f"no longer prints it")


def test_the_guide_never_promises_a_live_step_will_work_offline():
    """A participant on the offline path must never hit a command that needs a
    tenant without the guide having said so first."""
    text = GUIDE.read_text()
    for live_command in ("op climb", "op incident", "op restore", "op backup"):
        if live_command in text:
            assert "LIVE" in text, (
                f"{live_command!r} appears in the guide with no LIVE marker anywhere")
