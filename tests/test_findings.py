"""Tier 2 (T2-4) – finding lifecycle state machine. No live tenant."""
from resops.evidence import FunctionResult, Outcome
from resops.assurance.findings import track_findings


def res(name, outcome):
    return FunctionResult(name, outcome, "summary")


def hist(*outcomes, fn="recover"):
    """Build history rows (oldest first) for one function."""
    return [{"run_at": f"t{i}", "outcomes": {fn: o}} for i, o in enumerate(outcomes)]


def one(results, history, run_at="now"):
    return track_findings("host", run_at, results, history)


def test_first_nonpass_is_open():
    f = one([res("recover", Outcome.GAP)], [])
    assert len(f) == 1
    assert f[0].status == "OPEN" and f[0].runs_open == 1 and f[0].since == "now"
    assert f[0].risk == "medium"          # recover is recovery-critical


def test_open_streak_counts_and_dates():
    f = one([res("recover", Outcome.FAIL)], hist("GAP", "FAIL"))
    assert f[0].status == "OPEN"
    assert f[0].runs_open == 3            # two history + this run
    assert f[0].since == "t0"            # streak began at the oldest non-PASS
    assert f[0].risk == "high"           # recover FAIL


def test_remediated_when_just_fixed():
    f = one([res("recover", Outcome.PASS)], hist("GAP"))
    assert [x.status for x in f] == ["REMEDIATED"]


def test_verified_when_fix_held_a_cycle():
    f = one([res("recover", Outcome.PASS)], hist("GAP", "PASS"))
    assert [x.status for x in f] == ["VERIFIED"]


def test_stable_pass_produces_no_finding():
    assert one([res("recover", Outcome.PASS)], hist("PASS", "PASS")) == []


def test_regression_reopens_with_same_id():
    opened = one([res("recover", Outcome.GAP)], [])[0]
    reopened = one([res("recover", Outcome.GAP)], hist("GAP", "PASS", "PASS"))[0]
    assert opened.id == reopened.id      # stable id across close/reopen
    assert reopened.status == "OPEN"


def test_skip_is_not_a_finding():
    assert one([res("validate", Outcome.SKIP)], []) == []


def test_to_dict_trims_fields_by_status():
    open_f = one([res("recover", Outcome.GAP)], [])[0].to_dict()
    assert {"risk", "runs_open", "since"} <= open_f.keys()
    rem_f = one([res("recover", Outcome.PASS)], hist("GAP"))[0].to_dict()
    assert "risk" not in rem_f           # only OPEN carries risk/age
