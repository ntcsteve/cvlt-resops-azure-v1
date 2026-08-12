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
        "module": "M2.4 — publish the judgment",
        "command": "python3 -m resops metrics config/estate.yaml",
        "exit_code": 0,
        "must_contain": ["resops_rung", "resops_promotable", "resops_tolerated"],
    },
    {
        "module": "M5.4 — four recovery points",
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
    {
        # Runs after M5.4 in the guide, which is what writes the chain it audits.
        "module": "M5.5 — the audit trail",
        "command": "python3 -m resops verify config/incident.yaml",
        "exit_code": 0,
        "must_contain": ["audit trail intact"],
    },
]

# Files the PUBLISHED guides point at. A dead link in a room is a facilitator
# improvising, so they are checked like anything else.
LINKED_FILES = ("WORKSHEETS.md", "VERIFY.md", "RESOPS.md",
                "README.md", ".github/workflows/resops-gate.yml",
                "config/estate.yaml", "config/incident.yaml")

# Gitignored: it carries delivery coaching, the "what you must not claim" list,
# and tenant-specific investigation detail, so it is shared directly rather than
# published. Present for a maintainer, absent in a fresh clone — checked only
# when it is there, so the suite passes in both.
PRIVATE_DOCS = ("FACILITATOR.md",)


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


def test_every_metric_the_docs_name_actually_exists():
    """The docs show ILLUSTRATIVE metric blocks — labels trimmed, values chosen
    for the story — so they cannot be matched literally. Metric NAMES can be, and
    that is the half that goes stale: a renamed or invented series sends someone
    to build a dashboard panel that will never match anything.

    This exists because the README briefly claimed
    `resops_tolerated{workload="reporting-db"} 1` when the shipped estate emits 0.
    Same illustration-vs-reality trap the guide test was written for."""
    _, output = _run("python3 -m resops metrics config/estate.yaml")
    real = {line.split("{")[0].split(" ")[0]
            for line in output.splitlines() if line.startswith("resops_")}
    docs = ["README.md", "RESOPS.md", "WORKSHOP.md"]
    docs += [d for d in PRIVATE_DOCS if (ROOT / d).exists()]
    for doc in docs:
        for named in set(re.findall(r"\bresops_[a-z_]+\b", (ROOT / doc).read_text())):
            assert named in real, f"{doc} names {named}, which the tool never emits"


def test_every_file_the_guides_point_at_exists():
    """A dead link in a room is a facilitator improvising."""
    for name in LINKED_FILES:
        assert (ROOT / name).exists(), f"{name} is referenced by the guides but missing"


def test_the_published_guides_cross_reference_each_other():
    """Someone landing cold on one published doc must find the others."""
    guide = GUIDE.read_text()
    assert "WORKSHEETS.md" in guide
    assert "WORKSHOP.md" in (ROOT / "WORKSHEETS.md").read_text()


def test_the_published_guides_never_link_to_a_private_doc():
    """A markdown link to a gitignored file is a 404 for everyone who clones.
    The runbook is referred to in prose on purpose, never linked."""
    for doc in ("README.md", "WORKSHOP.md", "WORKSHEETS.md", "RESOPS.md", "VERIFY.md"):
        text = (ROOT / doc).read_text()
        for private in PRIVATE_DOCS:
            assert f"]({private})" not in text, (
                f"{doc} links to {private}, which is gitignored — that link is "
                f"broken in every clone")


def test_the_guide_never_promises_a_live_step_will_work_offline():
    """A participant on the offline path must never hit a command that needs a
    tenant without the guide having said so first."""
    text = GUIDE.read_text()
    for live_command in ("op climb", "op incident", "op restore", "op backup"):
        if live_command in text:
            assert "LIVE" in text, (
                f"{live_command!r} appears in the guide with no LIVE marker anywhere")

# --------------------------------------------------------------------------- #
# The estate demo's SHAPE, pinned workload by workload.
#
# WHY THIS EXISTS. On 2026-08-12 a new rule at the Scan rung moved identity-svc
# from "blocked at Validate" to "blocked at Scan", and 201 tests stayed green.
# The commands still ran, the exit codes still matched, every substring the guide
# quotes was still printed — and M1's entire lesson had changed, because that
# lesson is not a substring. It is WHICH workload stops WHERE:
#
#   "checkout-api and identity-svc sit on the SAME rung for opposite reasons —
#    one was tested and is contaminated, one was never tested. The rung hides
#    that. The blocked stage names it."
#
# If two workloads stop at the same stage, that paragraph is false and the module
# has no punchline. A substring check cannot see it. This can.
# --------------------------------------------------------------------------- #
ESTATE_LADDER = {
    "payments-api": ("VALIDATED", None),          # promotes, the control
    "checkout-api": ("RECOVERABLE", "Scan"),      # tested, and contaminated
    "identity-svc": ("RECOVERABLE", "Validate"),  # verified, never proven
    "reporting-db": ("PROTECTED", "Detect"),      # last backup failed
    "edge-cache": ("MONITORED", "Recover"),       # SLA missed
    "legacy-batch": ("UNDISCOVERED", "Discover"),  # never onboarded
}


def _parse_ladder(output: str) -> dict:
    """{workload: (state, blocked_stage_or_None)} from the rendered gate output.

    Deliberately parses what a ROOM SEES rather than calling the engine, because
    the thing being protected is the guide's promise about the screen.
    """
    found, current = {}, None
    for line in ANSI.sub("", output).splitlines():
        stripped = line.strip()
        if stripped.startswith("\u25b8 "):
            current = stripped[2:].split()[0]
            continue
        if current and any(s in stripped for s in
                           ("VALIDATED", "RECOVERABLE", "PROTECTED", "MONITORED",
                            "UNDISCOVERED", "DISCOVERED", "TRUSTED")):
            state = next(w for w in stripped.split() if w.isupper() and w.isalpha())
            stage = stripped.split("blocked at ")[1].split()[0] if "blocked at " in stripped else None
            found[current] = (state, stage)
            current = None
    return found


def test_the_estate_demo_stops_each_workload_where_the_guide_says():
    code, output = _run("python3 -m resops gate config/estate.yaml")
    assert code == 1
    actual = _parse_ladder(output)
    assert actual == ESTATE_LADDER, (
        "the estate demo changed shape. M1 teaches WHICH workload stops WHERE, so "
        "a moved rung rewrites the lesson without touching WORKSHOP.md.\n"
        f"  expected {ESTATE_LADDER}\n  actual   {actual}")


def test_the_two_recoverable_workloads_stop_for_DIFFERENT_reasons():
    """M1's punchline, asserted directly. Same rung, different stage. If these two
    ever collapse onto one stage the module loses the point it exists to make."""
    contaminated = ESTATE_LADDER["checkout-api"]
    never_proven = ESTATE_LADDER["identity-svc"]
    assert contaminated[0] == never_proven[0] == "RECOVERABLE"
    assert contaminated[1] != never_proven[1]
    code, output = _run("python3 -m resops gate config/estate.yaml")
    actual = _parse_ladder(output)
    assert actual["checkout-api"][1] != actual["identity-svc"][1]
