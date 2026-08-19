"""Tier 1 tests – tamper-evident history (T1-1) + scaffold smoke (T1-2/T1-3)."""
import json

from resops.assurance.capabilities import CAPABILITIES
from resops.assurance.controls import (
    FRAMEWORKS_DIR, load_controls, load_framework, resolve_controls,
)
from resops.evidence import (
    GENESIS_HASH, Bundle, FunctionResult, Outcome,
    append_history, load_history, verify_history,
)
from resops.assurance.report import render_markdown, risk_rating


def seed(path, n=3):
    for i in range(n):
        append_history(path, {"run_at": f"t{i}", "target": "h", "outcomes": {"recover": "PASS"}})


# --- T1-1: hash chain ------------------------------------------------------- #
def test_chain_links_and_verifies(tmp_path):
    path = tmp_path / "history.jsonl"
    seed(path, 3)
    rows = load_history(path)
    assert rows[0]["prev_hash"] == GENESIS_HASH
    assert rows[1]["prev_hash"] == rows[0]["entry_hash"]
    assert rows[2]["prev_hash"] == rows[1]["entry_hash"]
    assert verify_history(path) == (True, None)


def test_tamper_is_detected(tmp_path):
    path = tmp_path / "history.jsonl"
    seed(path, 3)
    rows = [json.loads(l) for l in path.read_text().splitlines()]
    rows[1]["outcomes"]["recover"] = "FAIL"          # forge a past record
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    ok, broken = verify_history(path)
    assert ok is False
    assert broken == 1


def test_empty_and_missing_history_ok(tmp_path):
    assert verify_history(tmp_path / "none.jsonl") == (True, None)


def test_legacy_unchained_prefix_skipped(tmp_path):
    path = tmp_path / "history.jsonl"
    path.write_text(json.dumps({"run_at": "old", "target": "h"}) + "\n")  # no hashes
    append_history(path, {"run_at": "new", "target": "h", "outcomes": {}})
    assert verify_history(path) == (True, None)


# --- T1-2 / crosswalk: framework resolution --------------------------------- #
def test_no_frameworks_resolves_to_none():
    assert load_controls({}) is None
    assert resolve_controls([]) is None


def test_single_framework_maps_capabilities():
    r = resolve_controls(["dora"])
    assert [f["id"] for f in r["frameworks"]] == ["dora"]
    # recover evidences CAP-RECOVERY-READINESS, with a DORA reference
    entry = r["controls"]["recover"][0]
    assert entry["id"] == "CAP-RECOVERY-READINESS"
    assert "dora" in entry["references"]


def test_multiple_frameworks_interchangeable_on_one_capability():
    r = resolve_controls(["dora", "nist-800-53", "apra-cps230"])
    refs = r["crosswalk"]["CAP-RESTORE-TESTED"]["references"]
    assert set(refs) == {"dora", "nist-800-53", "apra-cps230"}   # same capability, 3 regimes
    assert "Art. 11/12" in refs["dora"]
    assert "CP-4" in refs["nist-800-53"]


def test_framework_packs_only_reference_real_capabilities():
    """The guardrail: a pack may only reference capabilities that exist in code.

    An orphan reference (a typo, or drift after a capability is renamed) silently
    fails to render – inventing no false coverage – but it's still a bug: the pack
    claims a mapping the code can't back. Fail loud here so packs stay honest."""
    valid = {cap["id"] for caps in CAPABILITIES.values() for cap in caps}
    packs = sorted(FRAMEWORKS_DIR.glob("*.yaml"))
    assert packs, "no framework packs found in config/frameworks/"
    for path in packs:
        orphans = set(load_framework(path.stem).get("references", {})) - valid
        assert not orphans, f"{path.name} references unknown capabilities: {sorted(orphans)}"


def test_unknown_framework_fails_loud():
    try:
        resolve_controls(["does-not-exist"])
        assert False, "expected FileNotFoundError"
    except FileNotFoundError as e:
        assert "does-not-exist" in str(e)


# --- T1-2: bundle tagging --------------------------------------------------- #
CONTROLS = {
    "version": 1, "disclaimer": "Indicative only.",
    "controls": {
        "recover": [{"id": "CTRL-RECOVER-READINESS"}],
        "continuous_business": [{"id": "CTRL-GOVERNED-PROMOTION"}],
    },
}


def test_bundle_tags_functions_and_compliance():
    b = Bundle("h", "now", [FunctionResult("recover", Outcome.PASS, "ok")],
               gate={"decision": "PROMOTE", "reasons": []}, controls=CONTROLS)
    d = b.to_dict()
    assert d["functions"][0]["controls"][0]["id"] == "CTRL-RECOVER-READINESS"
    assert d["gate"]["controls"][0]["id"] == "CTRL-GOVERNED-PROMOTION"
    assert d["compliance"]["disclaimer"] == "Indicative only."


def test_repeated_to_dict_does_not_accumulate_gate_controls():
    b = Bundle("h", "now", [FunctionResult("recover", Outcome.PASS, "ok")],
               gate={"decision": "PROMOTE", "reasons": []}, controls=CONTROLS)
    assert len(b.to_dict()["gate"]["controls"]) == 1
    assert len(b.to_dict()["gate"]["controls"]) == 1   # not 2 – shared dict untouched
    assert "controls" not in b.gate                    # original verdict dict unmutated


def test_no_controls_means_no_compliance_block():
    b = Bundle("h", "now", [FunctionResult("recover", Outcome.PASS, "ok")])
    assert "compliance" not in b.to_dict()


# --- T1-3 report ------------------------------------------------------------ #
def test_risk_rating_scale():
    assert risk_rating("recover", "FAIL") == "high"
    assert risk_rating("detect", "GAP") == "low"
    assert risk_rating("recover", "PASS") == "none"


def test_report_renders_table_gate_and_controls():
    bundle = {
        "run_at": "t", "target": "h", "summary": {"pass": 1},
        "functions": [{"function": "recover", "outcome": "PASS", "summary": "ok",
                       "controls": [{"id": "CTRL-RECOVER-READINESS"}]}],
        "gate": {"decision": "PROMOTE", "reasons": []},
        "compliance": {"disclaimer": "Indicative only."},
    }
    md = render_markdown(bundle)
    assert "| recover | PASS | none | CTRL-RECOVER-READINESS | ok |" in md
    assert "Continuous Service:** PROMOTE" in md
    assert "_Indicative only._" in md
