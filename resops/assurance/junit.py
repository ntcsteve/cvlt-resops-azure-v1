"""
JUnit XML emitter — findings where engineers already look.

Every CI (GitHub, GitLab, Jenkins, Circle) renders JUnit natively, so this is
the portable way to surface a run as pass/fail test cases. The mapping is the
natural one: a workload is a test SUITE, each ResOps function a test CASE, a
GAP/FAIL a failure, a SKIP skipped. The gate verdict rides along as one decisive
case that fails on HOLD — so a blocked promotion shows up red in the test report.
"""
from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

# A non-PASS outcome on a function is a CI failure; SKIP is skipped.
FAIL_OUTCOMES = ("GAP", "FAIL")


def render_junit(bundle: dict, suite_name: str) -> str:
    """Render one workload's bundle dict as a <testsuites> JUnit document."""
    functions = bundle.get("functions", [])
    gate = bundle.get("gate")

    cases, failures, skipped = [], 0, 0
    for fn in functions:
        outcome, summary = fn["outcome"], fn.get("summary", "")
        case = {"classname": suite_name, "name": fn["function"]}
        if outcome in FAIL_OUTCOMES:
            failures += 1
            case["failure"] = f"{outcome}: {summary}"
        elif outcome == "SKIP":
            skipped += 1
            case["skipped"] = summary
        cases.append(case)

    if gate:                                  # the promotion decision as a test case
        case = {"classname": suite_name, "name": "Continuous Service (gate)"}
        if gate["decision"] == "HOLD":
            failures += 1
            case["failure"] = "HOLD: " + "; ".join(gate.get("reasons", []) or ["blocked"])
        cases.append(case)

    suite = ET.Element("testsuite", name=suite_name, tests=str(len(cases)),
                       failures=str(failures), skipped=str(skipped))
    for c in cases:
        tc = ET.SubElement(suite, "testcase", classname=c["classname"], name=c["name"])
        if "failure" in c:
            ET.SubElement(tc, "failure", message=_attr(c["failure"]))
        elif "skipped" in c:
            ET.SubElement(tc, "skipped", message=_attr(c["skipped"]))
    suites = ET.Element("testsuites", tests=str(len(cases)), failures=str(failures))
    suites.append(suite)
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(suites, encoding="unicode") + "\n"


def write_junit(bundle: dict, suite_name: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_junit(bundle, suite_name))


def _attr(text: str) -> str:
    """Trim + escape a message for an XML attribute."""
    return escape(text)[:300]
