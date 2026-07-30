"""P1 — the readiness ladder truth table. Pure classify(), no tenant, no clock.

Each test pins one rung: the reads that clear it, and the two ways it can block —
a real gap (intent unmet) and a read error (we couldn't verify). A read error
must NEVER produce a state above the rung below it.
"""
from resops.state import Reads, State, classify, trend

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


def _scan(*, clean=True, infected=0, fingerprint=0, **extra):
    """A parsed threat verdict, the shape reads.anomaly_verdict returns."""
    return {"clean": clean, "infectedFilesCount": infected,
            "fingerPrintFilesCount": fingerprint, **extra}


def _full_reads(**overrides) -> Reads:
    base = dict(vm_name=VM, vmgroup=_group(), vm=_vm(), anomaly=_scan(), proof=_proof())
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


def test_restore_disabled_stays_monitored():
    ladder = classify(_full_reads(vm=_vm(restore=False)))
    assert ladder.state is State.MONITORED


def test_no_successful_backup_stays_monitored():
    ladder = classify(_full_reads(vm=_vm(last_success=0)))
    assert ladder.state is State.MONITORED


# --------------------------------------------------------------------------- #
# Scan — is the point we'd restore from carrying a known threat?
#
# This is the rung the workshop turns on: a workload can be perfectly recoverable
# and still be untrustworthy, because the compromise is INSIDE the backup. A dirty
# verdict must never reach VALIDATED, however green everything below it looks.
# --------------------------------------------------------------------------- #
def test_clean_scan_clears_the_rung():
    ladder = classify(_full_reads())
    scan = next(r for r in ladder.rungs if r.stage == "Scan")
    assert scan.passed is True
    assert scan.evidence["threat_clean"] is True


def test_infected_recovery_point_stays_recoverable():
    ladder = classify(_full_reads(anomaly=_scan(clean=False, infected=3)))
    assert ladder.state is State.RECOVERABLE
    assert ladder.blocked_stage == "Scan"
    assert ladder.blocked_by_error is False
    assert "threat detected" in ladder.reason
    assert "3 infected" in ladder.reason


def test_file_anomaly_alone_blocks_the_rung():
    # Mass encryption fires the file-anomaly signal with zero malware matches.
    ladder = classify(_full_reads(anomaly=_scan(clean=False, fingerprint=42)))
    assert ladder.state is State.RECOVERABLE
    assert ladder.blocked_stage == "Scan"


def test_a_dirty_scan_beats_a_proven_restore():
    # The whole point: proof of recovery does NOT redeem a compromised source.
    # Validate must never be reached, let alone cleared.
    ladder = classify(_full_reads(anomaly=_scan(clean=False, infected=1),
                                  proof=_proof(status="Completed")))
    assert ladder.promotable is False
    validate = next(r for r in ladder.rungs if r.stage == "Validate")
    assert validate.passed is None


def test_unreadable_verdict_blocks_rather_than_passes():
    # Fail closed: a verdict we can't parse is not a clean verdict.
    ladder = classify(_full_reads(anomaly=_scan(clean=False, unreadable="unknown shape")))
    assert ladder.state is State.RECOVERABLE
    assert "unknown shape" in ladder.reason


def test_scan_read_error_stays_recoverable_as_error():
    ladder = classify(_full_reads(anomaly=None, anomaly_error="HTTP 503"))
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
        (_full_reads(anomaly=_scan(clean=False, infected=1)), False),
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
