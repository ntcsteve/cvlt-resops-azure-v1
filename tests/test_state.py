"""P1 — the readiness ladder truth table. Pure classify(), no tenant, no clock.

Each test pins one rung: the reads that clear it, and the two ways it can block —
a real gap (intent unmet) and a read error (we couldn't verify). A read error
must NEVER produce a state above the rung below it.
"""
from resops.state import Reads, State, _lag, classify, trend

VM = "vm01"


# --------------------------------------------------------------------------- #
# Builders — a fully-VALIDATED set of reads, then knock out one rung at a time.
# --------------------------------------------------------------------------- #
def _group(*, in_group=True, plan="Gold-Plan", backup_status="COMPLETED", failure=""):
    vms = [{"name": VM}] if in_group else [{"name": "someone-else"}]
    return {
        "name": "Steve-VM-Group",
        "content": [{"virtualMachines": vms}],
        "summary": {"plan": {"name": plan}} if plan else {},
        "vmBackupInfo": {"vmProtectedCount": 1, "vmNotProtectedCount": 0, "vmTotalCount": 1},
        "lastBackup": {"status": backup_status, "failureReason": failure, "jobId": 7521683},
    }


def _vm(*, sla="Protected", restore=True, last_success=1_700_000_000):
    return {"name": VM, "slaCategoryDescription": sla, "isRestoreActivityEnabled": restore,
            "lastSuccessfulBackupTime": last_success, "strGUID": "guid-1"}


def _proof(status="Completed"):
    return {"jobId": 7540314, "status": status}


def _scan(*, clean=True, source="threatscan", detail="", at=1_700_000_060, **extra):
    """An attestation about ONE recovery point.

    `at` defaults to just AFTER _vm()'s lastSuccessfulBackupTime, because that is
    the only order reality produces: the drill restores a recovery point and then
    verifies it, so a genuine attestation is always newer than the point it
    describes. Omitting `at`, or setting it earlier than the newest point, blocks
    at Scan — see the coverage tests below.

    Note on `source`: threat_attestation() never returns clean=True (it reports
    negatives or nothing), so a clean fixture stands in for restore-verify.
    """
    return {"source": source, "clean": clean, "detail": detail, "at": at, **extra}


def _full_reads(**overrides) -> Reads:
    base = dict(vm_name=VM, vmgroup=_group(), vm=_vm(), attestation=_scan(), proof=_proof())
    base.update(overrides)
    return Reads(**base)


# --------------------------------------------------------------------------- #
# The happy path — every rung cleared.
# --------------------------------------------------------------------------- #
def test_full_climb_reaches_validated():
    ladder = classify(_full_reads())
    assert ladder.state is State.VALIDATED
    assert ladder.blocked_stage is None
    assert ladder.promotable is True
    assert "recovery proven" in ladder.reason
    assert [r.passed for r in ladder.rungs] == [True, True, True, True, True, True]


# --------------------------------------------------------------------------- #
# Discover — onboarded into a VM group at all?
# --------------------------------------------------------------------------- #
def test_not_in_group_stays_undiscovered():
    ladder = classify(_full_reads(vmgroup=_group(in_group=False)))
    assert ladder.state is State.UNDISCOVERED
    assert ladder.blocked_stage == "Discover"
    assert ladder.blocked_by_error is False


def test_group_read_error_stays_undiscovered_as_error():
    ladder = classify(_full_reads(vmgroup={}, vmgroup_error="HTTP 403"))
    assert ladder.state is State.UNDISCOVERED
    assert ladder.blocked_stage == "Discover"
    assert ladder.blocked_by_error is True
    assert "403" in ladder.reason


def test_missing_vm_name_is_a_config_error():
    ladder = classify(Reads(vm_name=""))
    assert ladder.state is State.UNDISCOVERED
    assert ladder.blocked_by_error is True


# --------------------------------------------------------------------------- #
# Protect — is a plan attached?
# --------------------------------------------------------------------------- #
def test_no_plan_stays_discovered():
    ladder = classify(_full_reads(vmgroup=_group(plan="")))
    assert ladder.state is State.DISCOVERED
    assert ladder.blocked_stage == "Protect"
    assert ladder.blocked_by_error is False


# --------------------------------------------------------------------------- #
# Detect — did the last backup complete cleanly?
# --------------------------------------------------------------------------- #
def test_no_backup_yet_stays_protected():
    ladder = classify(_full_reads(vmgroup=_group(backup_status="")))
    assert ladder.state is State.PROTECTED
    assert ladder.blocked_stage == "Detect"


def test_failed_backup_stays_protected():
    ladder = classify(_full_reads(vmgroup=_group(backup_status="FAILED", failure="snapshot error")))
    assert ladder.state is State.PROTECTED
    assert ladder.blocked_stage == "Detect"
    assert "snapshot error" in ladder.reason


def test_long_failure_reason_clips_at_a_word_boundary():
    long = "Virtual machine [MetallicPOCWalkThrough] was not found. Please verify that the configuration"
    ladder = classify(_full_reads(vmgroup=_group(backup_status="FAILED", failure=long)))
    assert ladder.reason.endswith(" …")             # ellipsis with a space, not mid-word
    shown = ladder.reason.split("— ", 1)[1][:-2].rstrip()   # the clipped failure, minus " …"
    assert long.startswith(shown)                   # a clean prefix — no chopped word
    assert len(shown) < len(long)                   # it actually clipped


# --------------------------------------------------------------------------- #
# Recover — recent, recoverable, SLA-Protected point?
# --------------------------------------------------------------------------- #
def test_vm_not_among_protected_stays_monitored():
    ladder = classify(_full_reads(vm=None))
    assert ladder.state is State.MONITORED
    assert ladder.blocked_stage == "Recover"
    assert ladder.blocked_by_error is False


def test_vm_read_error_stays_monitored_as_error():
    ladder = classify(_full_reads(vm=None, vm_error="HTTP 500"))
    assert ladder.state is State.MONITORED
    assert ladder.blocked_by_error is True


def test_sla_not_met_stays_monitored():
    ladder = classify(_full_reads(vm=_vm(sla="Missed SLA")))
    assert ladder.state is State.MONITORED
    assert "SLA not met" in ladder.reason


def test_SLA_NOT_YET_EVALUATED_DOES_NOT_BLOCK():
    """"N/A" (slaStatus 3) means Commvault's periodic SLA job has not classified
    this workload YET. It used to block, and that was wrong twice over.

    Wrong on the facts: the field is a CACHED BATCH VERDICT, not a live one. It
    read "N/A" for 29 minutes on a workload we had just backed up, restored and
    verified clean, while three VMs DELETED from Azure still read "Protected" in
    the same tenant. Unreliable in both directions.

    Wrong on the layering: this rung asks a CAPABILITY question — is there a
    restorable point — and lastSuccessfulBackupTime plus isRestoreActivityEnabled
    answer it. RECENCY is policy, it needs a clock, and classify() has none by
    design. The gate owns it, and M5.4's A-400-days-ago already proves the split:
    it reaches VALIDATED at RPO 9600h and the GATE stops it.

    Cost of the old behaviour: every new workload dead for half an hour, looking
    exactly like a broken checkout. On workshop day, the whole room at once.
    """
    for sla in ("N/A", ""):
        ladder = classify(_full_reads(vm=_vm(sla=sla)))
        assert ladder.state is State.VALIDATED
        assert "not evaluated" in ladder.reason or ladder.blocked_stage is None


def test_an_sla_verdict_that_was_made_and_says_missed_still_blocks():
    """Absence attests nothing. A verdict that EXISTS and says "not met" is real
    information, and it still blocks — exactly as the Scan rung treats a recorded
    anomaly versus a missing one."""
    ladder = classify(_full_reads(vm=_vm(sla="Missed SLA")))
    assert ladder.state is State.MONITORED
    assert ladder.blocked_stage == "Recover"
    assert "SLA not met" in ladder.reason


def test_the_recover_rung_records_whether_the_vendor_had_evaluated():
    """"We did not know" must be visible in the evidence, not silent. The gate
    reads this to decide whether anything can judge recency at all."""
    from resops.state import sla_evaluated

    assert sla_evaluated({"slaCategoryDescription": "Protected"}) is True
    assert sla_evaluated({"slaCategoryDescription": "Missed SLA"}) is True
    assert sla_evaluated({"slaCategoryDescription": "N/A"}) is False
    assert sla_evaluated({"slaCategoryDescription": ""}) is False
    assert sla_evaluated({}) is False
    assert sla_evaluated(None) is False


def test_restore_disabled_stays_monitored():
    ladder = classify(_full_reads(vm=_vm(restore=False)))
    assert ladder.state is State.MONITORED


def test_no_successful_backup_stays_monitored():
    ladder = classify(_full_reads(vm=_vm(last_success=0)))
    assert ladder.state is State.MONITORED


# --------------------------------------------------------------------------- #
# Scan — has ANYONE attested the point we'd restore from?
#
# The rung the workshop turns on, and the rung that taught us the hardest lesson.
# It used to clear whenever no anomaly was recorded — which sounds reasonable and
# is wrong, because a scan that never ran records no anomaly either. An
# unattested recovery point is now a BLOCK.
#
# The lesson survived a correction. For six weeks we also believed no scan here
# had ever examined anything; on 2026-08-12 one reported two planted EICAR files.
# The rule was right, the reason given for it was not, and the tests below never
# depended on the reason.
# --------------------------------------------------------------------------- #
def test_an_unattested_point_blocks_the_rung():
    # THE regression guard. Nobody checked, so nobody may promote.
    ladder = classify(_full_reads(attestation=None))
    assert ladder.state is State.RECOVERABLE
    assert ladder.blocked_stage == "Scan"
    assert ladder.blocked_by_error is False
    assert "UNATTESTED" in ladder.reason


def test_a_positive_attestation_clears_the_rung():
    ladder = classify(_full_reads(attestation=_scan(clean=True, detail="746 files")))
    scan = next(r for r in ladder.rungs if r.stage == "Scan")
    assert scan.passed is True
    assert scan.evidence["attested_clean"] is True
    assert scan.evidence["attested_by"] == "threatscan"


# --------------------------------------------------------------------------- #
# COVERAGE — does the attestation describe the point we would actually restore?
#
# THE BUG THESE GUARD, and it was ours, live, on 2026-08-12. The gate returned
# ●●●●●● VALIDATED · PROMOTE · exit 0 for a workload whose newest recovery point
# held two EICAR files and fourteen encrypted ones, because the attestation was
# clean, 51 minutes older than that point, and only 0.0 days old. It then wrote a
# framework-mapped compliance report saying the same thing.
#
# An attestation is a claim about ONE recovery point. Age is policy and lives in
# the gate. Coverage is capability and lives here. The numbers below are the real
# ones from that run, scaled to the fixture clock.
# --------------------------------------------------------------------------- #
def test_an_attestation_older_than_the_newest_point_does_not_cover_it():
    # backup at 1_700_003_600, attestation 51 minutes earlier. The exact shape of
    # the live failure: clean, recent, and about a point that no longer matters.
    ladder = classify(_full_reads(vm=_vm(last_success=1_700_003_600),
                                  attestation=_scan(clean=True, at=1_700_000_540)))
    assert ladder.state is State.RECOVERABLE
    assert ladder.blocked_stage == "Scan"
    assert "does not cover" in ladder.reason
    scan = next(r for r in ladder.rungs if r.stage == "Scan")
    assert scan.evidence["attested_at"] == 1_700_000_540
    assert scan.evidence["newest_recovery_point"] == 1_700_003_600


def test_an_attestation_newer_than_the_newest_point_clears():
    # The drill runs AFTER the backup it verifies, which is the only real order.
    ladder = classify(_full_reads(vm=_vm(last_success=1_700_003_600),
                                  attestation=_scan(clean=True, at=1_700_003_700)))
    assert ladder.state is State.VALIDATED
    assert ladder.blocked_stage is None


def test_a_clean_attestation_with_no_timestamp_fails_closed():
    """Without a timestamp an attestation cannot be shown to cover anything, so
    it must not clear the rung. Fails closed rather than assuming it is current."""
    att = _scan(clean=True)
    del att["at"]
    ladder = classify(_full_reads(attestation=att))
    assert ladder.state is State.RECOVERABLE
    assert ladder.blocked_stage == "Scan"
    assert "no timestamp" in ladder.reason


def test_coverage_never_overrides_a_dirty_verdict():
    """A dirty attestation blocks as DIRTY, not as uncovered. The reader needs the
    worse fact, and the two have different fixes."""
    ladder = classify(_full_reads(vm=_vm(last_success=1_700_003_600),
                                  attestation=_scan(clean=False, detail="14 encrypted files",
                                                    at=1_700_000_540)))
    assert ladder.blocked_stage == "Scan"
    assert "14 encrypted files" in ladder.reason
    assert "does not cover" not in ladder.reason


def test_the_evidence_names_who_attested():
    # An attestation is only worth anything if you can say who made it.
    ladder = classify(_full_reads(attestation=_scan(source="restore-verify", clean=True)))
    scan = next(r for r in ladder.rungs if r.stage == "Scan")
    assert scan.evidence["attested_by"] == "restore-verify"


def test_a_failed_attestation_stays_recoverable():
    ladder = classify(_full_reads(attestation=_scan(clean=False, detail="3 infected")))
    assert ladder.state is State.RECOVERABLE
    assert ladder.blocked_stage == "Scan"
    assert ladder.blocked_by_error is False
    assert "3 infected" in ladder.reason


def test_a_dirty_point_beats_a_proven_restore():
    # Proof of recovery does NOT redeem a compromised source. Validate must never
    # be reached, let alone cleared.
    ladder = classify(_full_reads(attestation=_scan(clean=False, detail="1 infected"),
                                  proof=_proof(status="Completed")))
    assert ladder.promotable is False
    validate = next(r for r in ladder.rungs if r.stage == "Validate")
    assert validate.passed is None


def test_attestation_read_error_stays_recoverable_as_error():
    ladder = classify(_full_reads(attestation=None, attestation_error="HTTP 503"))
    assert ladder.state is State.RECOVERABLE
    assert ladder.blocked_stage == "Scan"
    assert ladder.blocked_by_error is True


# --------------------------------------------------------------------------- #
# Validate — has a real restore proven recovery?
# --------------------------------------------------------------------------- #
def test_no_proof_stays_recoverable():
    ladder = classify(_full_reads(proof=None))
    assert ladder.state is State.RECOVERABLE
    assert ladder.blocked_stage == "Validate"
    assert ladder.blocked_by_error is False


def test_proof_read_error_stays_recoverable_as_error():
    ladder = classify(_full_reads(proof=None, proof_error="HTTP 403"))
    assert ladder.state is State.RECOVERABLE
    assert ladder.blocked_by_error is True


def test_failed_restore_stays_recoverable():
    ladder = classify(_full_reads(proof=_proof(status="Failed")))
    assert ladder.state is State.RECOVERABLE
    assert "not clean" in ladder.reason


# --------------------------------------------------------------------------- #
# Invariants — properties that must hold for every reachable ladder.
# --------------------------------------------------------------------------- #
def test_blocked_marks_exactly_one_stage_and_truncates_the_rest():
    ladder = classify(_full_reads(vmgroup=_group(backup_status="")))  # blocked at Detect
    passed = [r.passed for r in ladder.rungs]
    assert passed == [True, True, False, None, None, None]  # cleared×2, blocked, not reached×3


def test_state_ordering_is_total():
    assert State.UNDISCOVERED < State.PROTECTED < State.TRUSTED < State.VALIDATED
    assert State.VALIDATED.rank == 6


def test_only_validated_is_promotable():
    for reads, expected in [
        (_full_reads(), True),
        (_full_reads(proof=None), False),
        (_full_reads(attestation=_scan(clean=False, infected=1)), False),
        (_full_reads(vmgroup=_group(in_group=False)), False),
    ]:
        assert classify(reads).promotable is expected


# --------------------------------------------------------------------------- #
# Improve trend — the cross-cutting signal over history. Pure, no clock.
# --------------------------------------------------------------------------- #
def _hist(*states):
    return [{"state": s} for s in states]


def test_no_history_is_baseline():
    t = trend(State.VALIDATED, [])
    assert t.direction == "baseline"
    assert t.previous is None
    assert t.runs == 1
    assert t.regressed is False


def test_climb_is_not_a_regression():
    t = trend(State.VALIDATED, _hist("MONITORED"))
    assert t.direction == "climbed"
    assert t.previous is State.MONITORED
    assert t.regressed is False
    assert "MONITORED→VALIDATED" in t.summary


def test_regression_drops_a_rung_and_flags_the_gate():
    t = trend(State.RECOVERABLE, _hist("VALIDATED"))
    assert t.direction == "regressed"
    assert t.regressed is True
    assert "VALIDATED→RECOVERABLE" in t.summary


def test_held_counts_the_streak():
    t = trend(State.VALIDATED, _hist("MONITORED", "VALIDATED", "VALIDATED"))
    assert t.direction == "held"
    assert t.regressed is False
    assert "over 3 runs" in t.summary          # 2 trailing + this run
    assert t.runs == 4


def test_legacy_entries_without_state_are_not_comparable():
    # Pre-ladder history stored per-function outcomes, no `state` field.
    legacy = [{"outcomes": {"recover": "PASS"}}, {"outcomes": {"recover": "GAP"}}]
    t = trend(State.VALIDATED, legacy)
    assert t.direction == "baseline"           # nothing comparable yet
    assert t.runs == 3                          # but run count still reflects history


def test_trend_uses_most_recent_comparable_state():
    # legacy entry then a ladder entry — compare against the ladder one.
    mixed = [{"outcomes": {}}, {"state": "VALIDATED"}]
    t = trend(State.PROTECTED, mixed)
    assert t.direction == "regressed"
    assert t.previous is State.VALIDATED

def test_a_sub_hour_lag_reads_in_minutes_not_as_zero():
    """It printed "verified 0.0h before it was taken" the first time it fired live,
    for a two-minute gap. A rounded zero in a blocking reason reads as a broken
    tool, and this string is what someone acts on at 2am."""
    assert _lag(120) == "2 min"
    assert _lag(3599) == "60 min"
    assert _lag(2.6 * 3600) == "2.6h"
    assert _lag(47 * 86400) == "47.0d"
