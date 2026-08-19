"""Tier 2 (T2-5) – workload resolution + slug. Pure helpers, no tenant."""
from pathlib import Path

from resops.__main__ import ROOT, _display, _looks_like_command, _slug, _workloads, main


def test_singular_workload_is_flat():
    wl, flat = _workloads({"workload": {"vm_name": "vm01", "vm_group_id": 1}})
    assert flat is True
    assert len(wl) == 1
    assert wl[0]["name"] == "vm01"                 # name defaults to vm_name
    assert wl[0]["criticality"] == "unspecified"


def test_workloads_list_is_not_flat():
    wl, flat = _workloads({"workloads": [
        {"name": "payments", "vm_name": "a", "vm_group_id": 1, "criticality": "critical"},
        {"vm_name": "b", "vm_group_id": 2},
    ]})
    assert flat is False
    assert [w["name"] for w in wl] == ["payments", "b"]
    assert wl[0]["criticality"] == "critical"
    assert wl[1]["criticality"] == "unspecified"   # default fills in


def test_empty_config_has_no_workloads():
    wl, flat = _workloads({})
    assert wl == [] and flat is True


def test_slug_is_filesystem_safe():
    assert _slug("Payments API / prod") == "payments-api---prod"
    assert _slug("vm-rwk-ws-0610a") == "vm-rwk-ws-0610a"
    assert _slug("!!!") == "workload"              # never empty


def test_display_is_relative_under_root_absolute_outside():
    # Under the repo → tidy relative path; outside (e.g. a CI artifacts dir) →
    # absolute, not a crash (regression: relative_to used to raise ValueError).
    assert _display(ROOT / "evidence" / "bundle.json") == "evidence/bundle.json"
    assert _display(Path("/tmp/ci/run/summary.json")) == "/tmp/ci/run/summary.json"


def test_looks_like_command_distinguishes_typos_from_configs():
    assert _looks_like_command("listt") is True            # mistyped subcommand
    assert _looks_like_command("config/x.yaml") is False   # a config path, not a command
    assert _looks_like_command("run.yml") is False


def test_help_prints_usage_and_exits_zero(capsys):
    assert main(["help"]) == 0
    assert main(["--help"]) == 0
    assert "Usage:" in capsys.readouterr().out


def test_unknown_command_is_usage_error(capsys):
    assert main(["listt"]) == 2                             # CONFIG_ERROR, not a crash
    assert "Unknown command: listt" in capsys.readouterr().out
