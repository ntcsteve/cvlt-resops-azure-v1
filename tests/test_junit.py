"""CI-native output (JUnit). No live tenant. (Gate policy lives in test_gate.py.)"""
from xml.etree import ElementTree as ET

from resops.assurance.junit import render_junit


def bundle(functions, gate=None):
    b = {"functions": functions}
    if gate:
        b["gate"] = gate
    return b


def fn(name, outcome, summary="ok"):
    return {"function": name, "outcome": outcome, "summary": summary}


# --- JUnit emitter ---------------------------------------------------------- #
def test_junit_is_wellformed_and_counts():
    xml = render_junit(bundle([
        fn("recover", "PASS"), fn("protect", "GAP", "not covered"),
        fn("validate", "SKIP", "no proof"),
    ]), "payments-api")
    suite = ET.fromstring(xml).find("testsuite")
    assert suite.get("name") == "payments-api"
    assert suite.get("tests") == "3"
    assert suite.get("failures") == "1"     # the GAP
    assert suite.get("skipped") == "1"      # the SKIP


def test_junit_gate_hold_is_a_failure_case():
    xml = render_junit(bundle([fn("recover", "PASS")],
                              gate={"decision": "HOLD", "reasons": ["rto 90m > target 60m"]}),
                       "wl")
    cases = ET.fromstring(xml).find("testsuite").findall("testcase")
    gate_case = [c for c in cases if "gate" in c.get("name")][0]
    failure = gate_case.find("failure")
    assert failure is not None
    assert "rto 90m" in failure.get("message")


def test_junit_promote_has_no_failures():
    xml = render_junit(bundle([fn("recover", "PASS"), fn("validate", "PASS")],
                              gate={"decision": "PROMOTE", "reasons": []}), "wl")
    assert ET.fromstring(xml).find("testsuite").get("failures") == "0"


def test_junit_escapes_special_chars():
    xml = render_junit(bundle([fn("recover", "GAP", "a < b & c > d")]), "wl")
    assert ET.fromstring(xml) is not None    # parses → escaping is correct
