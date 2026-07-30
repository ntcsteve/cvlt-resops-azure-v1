"""The threat-scan parsers — the write lane's first tests.

These cover the three derivations `op threatscan` makes before it can trigger a
scan: which storage pool, which copy actually holds the backup, and what the
post-scan verdict says. Each was discovered against the live API and each is easy
to get subtly wrong (the snap copy and the pool's own primary copy both look
plausible and are both wrong), so they're pinned here.

Note what these DON'T import: `resops.operator.op` reads config/workshop.yaml at
import time, and that file is gitignored — so a test that imported it would pass
on the author's machine and fail on a fresh clone. The parsers live in the read
layer precisely so this suite runs anywhere.
"""
from resops.reads import anomaly_verdict, default_copy_id, storage_pool_id


# --------------------------------------------------------------------------- #
# storage_pool_id — the id hides under storagePoolEntity, not at the top level.
# --------------------------------------------------------------------------- #
POOLS = {"storagePoolList": [
    {"storagePoolEntity": {"storagePoolName": "Other-Pool", "storagePoolId": 1111}},
    {"storagePoolEntity": {"storagePoolName": "ResOps-Workshop-AirGapProtect",
                           "storagePoolId": 6697}},
]}


def test_storage_pool_id_resolves_by_name():
    assert storage_pool_id(POOLS, "ResOps-Workshop-AirGapProtect") == 6697


def test_storage_pool_id_is_none_when_absent():
    # None, not an exception — the write lane turns it into a SystemExit with the fix.
    assert storage_pool_id(POOLS, "no-such-pool") is None


def test_storage_pool_id_survives_an_empty_response():
    assert storage_pool_id({}, "anything") is None


# --------------------------------------------------------------------------- #
# default_copy_id — the snap copy is a decoy. Scanning it is not scanning the backup.
# --------------------------------------------------------------------------- #
POLICY = {"copy": [
    {"isDefault": False, "StoragePolicyCopy": {"copyId": 9503, "copyName": "Primary Snap"}},
    {"isDefault": True, "StoragePolicyCopy": {"copyId": 9504, "copyName": "Primary"}},
]}


def test_default_copy_id_picks_the_default_not_the_snap():
    assert default_copy_id(POLICY) == 9504


def test_default_copy_id_is_none_when_no_copy_is_default():
    snap_only = {"copy": [POLICY["copy"][0]]}
    assert default_copy_id(snap_only) is None


# --------------------------------------------------------------------------- #
# anomaly_verdict — absence means clean; the API reports exceptions, not all-clears.
# --------------------------------------------------------------------------- #
def test_verdict_is_clean_when_the_client_has_no_anomaly_record():
    verdict = anomaly_verdict({"anomalyClients": []}, 12345)
    assert verdict == {"clean": True, "infectedFilesCount": 0, "fingerPrintFilesCount": 0}


def test_verdict_is_clean_when_counts_are_zero():
    body = {"anomalyClients": [{"client": {"clientId": 12345},
                                "infectedFilesCount": 0, "fingerPrintFilesCount": 0}]}
    assert anomaly_verdict(body, 12345)["clean"] is True


def test_infected_files_make_it_dirty():
    body = {"anomalyClients": [{"client": {"clientId": 12345},
                                "infectedFilesCount": 3, "fingerPrintFilesCount": 0}]}
    verdict = anomaly_verdict(body, 12345)
    assert verdict["clean"] is False
    assert verdict["infectedFilesCount"] == 3


def test_fingerprint_anomalies_alone_make_it_dirty():
    # File-anomaly detection (mass encryption) fires without any malware match —
    # a ransomware event can be all fingerprint and zero infected.
    body = {"anomalyClients": [{"client": {"clientId": 12345},
                                "infectedFilesCount": 0, "fingerPrintFilesCount": 42}]}
    assert anomaly_verdict(body, 12345)["clean"] is False


def test_another_clients_anomalies_do_not_taint_ours():
    body = {"anomalyClients": [{"client": {"clientId": 99999},
                                "infectedFilesCount": 500, "fingerPrintFilesCount": 500}]}
    assert anomaly_verdict(body, 12345)["clean"] is True
