"""Unit tests for the evidence contract — no live tenant needed."""

from resops.evidence import (
    SCHEMA_VERSION, Bundle, FunctionResult, Outcome,
    append_history, history_entry, load_history,
)


def make(name, outcome):
    return FunctionResult(name, outcome, f"{name} summary", {"n": 1})


def test_summary_counts():
    bundle = Bundle("host", "now", [
        make("a", Outcome.PASS), make("b", Outcome.GAP),
        make("c", Outcome.FAIL), make("d", Outcome.SKIP), make("e", Outcome.PASS),
    ])
    assert bundle.summary_counts() == {"pass": 2, "gap": 1, "fail": 1, "skip": 1}


def test_exit_code_counts_only_fails():
    assert Bundle("h", "n", [make("a", Outcome.PASS), make("b", Outcome.GAP)]).exit_code() == 0
    assert Bundle("h", "n", [make("a", Outcome.FAIL), make("b", Outcome.FAIL)]).exit_code() == 2


def test_bundle_dict_has_stable_shape():
    bundle = Bundle("tenant", "2026-01-01T00:00:00Z", [make("protect", Outcome.GAP)])
    d = bundle.to_dict()
    assert d["schema_version"] == SCHEMA_VERSION
    assert d["target"] == "tenant"
    assert d["run_at"] == "2026-01-01T00:00:00Z"
    assert d["summary"]["gap"] == 1
    fn = d["functions"][0]
    assert fn == {
        "function": "protect",
        "outcome": "GAP",
        "devops_lens": "like GitOps drift — declared vs actual coverage",
        "summary": "protect summary",
        "evidence": {"n": 1},
    }


def test_bundle_writes_json(tmp_path):
    out = tmp_path / "sub" / "bundle.json"
    Bundle("h", "n", [make("a", Outcome.PASS)]).write(out)
    assert out.exists()
    assert f'"schema_version": "{SCHEMA_VERSION}"' in out.read_text()


def test_history_append_and_load(tmp_path):
    path = tmp_path / "sub" / "history.jsonl"
    append_history(path, {"run_at": "t1", "outcomes": {"recover": "PASS"}})
    append_history(path, {"run_at": "t2", "outcomes": {"recover": "GAP"}})
    history = load_history(path)
    assert len(history) == 2
    assert history[-1]["run_at"] == "t2"


def test_load_history_missing_file_is_empty(tmp_path):
    assert load_history(tmp_path / "nope.jsonl") == []


def test_history_entry_captures_outcomes_and_metrics():
    results = [FunctionResult("recover", Outcome.PASS, "ok",
                              {"rpo_hours": 2.9, "sla_status": "Protected"})]
    entry = history_entry("t1", "tenant", results)
    assert entry["outcomes"] == {"recover": "PASS"}
    assert entry["metrics"] == {"rpo_hours": 2.9, "sla_status": "Protected"}
