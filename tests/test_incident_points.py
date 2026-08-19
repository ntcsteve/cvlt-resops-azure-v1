"""config/incident.yaml – the four-recovery-point decision, pinned.

This is a WORKSHOP ASSET, not just a demo. Its whole teaching turns on the gate
promoting exactly one point and that point being the one inside the incident
window. Change tier1's rpo_hours or attestation_max_age_days in config/tiers.yaml
and the exercise quietly becomes a different lesson, in a room, with no warning.
These tests are what makes that a failed build instead.

They also prove the relative-age resolver end to end: "6 days ago" has to still
mean six days whenever someone runs this, or the numbers stop matching the story.
"""
import json

import yaml

from resops.__main__ import ROOT, _resolve_ages, main

NOW = 1_800_000_000


# --------------------------------------------------------------------------- #
# The resolver.
# --------------------------------------------------------------------------- #
def test_offsets_resolve_to_epochs():
    assert _resolve_ages({"days_ago": 6}, NOW) == NOW - 6 * 86400
    assert _resolve_ages({"hours_ago": 7}, NOW) == NOW - 7 * 3600


def test_offsets_resolve_wherever_they_are_nested():
    out = _resolve_ages({"vm": {"last": {"days_ago": 1}},
                         "jobs": [{"at": {"hours_ago": 2}}]}, NOW)
    assert out["vm"]["last"] == NOW - 86400
    assert out["jobs"][0]["at"] == NOW - 7200


def test_real_payloads_are_never_mistaken_for_an_offset():
    """Only a dict whose keys are EXACTLY one offset converts. A fixed epoch, a
    null attestation, and any multi-key object all pass through untouched."""
    payload = {"days_ago": 6, "status": "Completed"}   # two keys – not an offset
    assert _resolve_ages(payload, NOW) == payload
    assert _resolve_ages({"at": 1785390783}, NOW) == {"at": 1785390783}
    assert _resolve_ages({"attestation": None}, NOW) == {"attestation": None}


# --------------------------------------------------------------------------- #
# The exercise itself, against the real committed fixtures.
# --------------------------------------------------------------------------- #
def _run(tmp_path):
    config = yaml.safe_load((ROOT / "config" / "incident.yaml").read_text())
    config["evidence_dir"] = str(tmp_path / "evidence")
    path = tmp_path / "incident.yaml"
    path.write_text(yaml.safe_dump(config))
    exit_code = main(["gate", str(path)])
    summary = json.loads((tmp_path / "evidence" / "summary.json").read_text())
    return exit_code, {w["name"]: w for w in summary["workloads"]}


def test_exactly_one_point_promotes_and_it_is_the_freshest(tmp_path):
    """THE EXERCISE. If this ever promotes two points, or none, or a different
    one, the dilemma is gone and M6 needs redesigning before it is delivered."""
    exit_code, points = _run(tmp_path)
    assert exit_code == 1
    promoted = [n for n, p in points.items() if p["gate"] == "PROMOTE"]
    assert promoted == ["D-7-hours-ago"]


def test_each_point_is_blocked_for_a_DIFFERENT_reason(tmp_path):
    """Four points, four distinct lessons. Two points blocked for the same
    reason would waste a slot."""
    _, points = _run(tmp_path)

    # C – the backup is fine and nobody ever looked inside it.
    assert points["C-32-hours-ago"]["blocked_stage"] == "Scan"

    # B – attested clean, blocked purely on data loss. The RPO was written for
    # outages, and the room has to decide whether it governs a compromise.
    b_bundle = json.loads((tmp_path / "evidence" / "b-6-days-ago" / "bundle.json").read_text())
    assert b_bundle["gate"]["decision"] == "HOLD"
    assert any("rpo" in r for r in b_bundle["gate"]["reasons"])
    assert points["B-6-days-ago"]["state"] == "VALIDATED"     # it CLIMBED. it still holds.

    # A – the only point outside any plausible incident window, and its
    # attestation is 400 days old because nobody drilled in between.
    a_bundle = json.loads((tmp_path / "evidence" / "a-400-days-ago" / "bundle.json").read_text())
    assert any("attestation stale" in r for r in a_bundle["gate"]["reasons"])


def test_the_ages_still_mean_what_the_scenario_says(tmp_path):
    """Relative offsets, end to end. If these drift the story stops matching the
    screen, which is exactly what fixed epochs did to the older demos."""
    _run(tmp_path)
    ages = {}
    for slug in ("d-7-hours-ago", "c-32-hours-ago", "b-6-days-ago", "a-400-days-ago"):
        bundle = json.loads((tmp_path / "evidence" / slug / "bundle.json").read_text())
        recover = [f for f in bundle["functions"] if f["function"] == "recover"][0]
        ages[slug] = recover["evidence"]["rpo_hours"]
    assert ages["d-7-hours-ago"] == 7.0
    assert ages["c-32-hours-ago"] == 32.0
    assert ages["b-6-days-ago"] == 144.0          # 6 days
    assert ages["a-400-days-ago"] == 9600.0       # 400 days


def test_the_unattested_point_carries_no_attestation_age(tmp_path):
    """C is not 'clean, age unknown'. It is unverified, and the absence has to
    stay absent rather than defaulting to a number a dashboard would chart."""
    _, points = _run(tmp_path)
    assert points["C-32-hours-ago"]["attestation_age_days"] is None
