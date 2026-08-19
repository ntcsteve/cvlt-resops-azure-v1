"""The threat-scan parsers – the write lane's first tests.

These cover the three derivations `op threatscan` makes before it can trigger a
scan: which storage pool, which copy actually holds the backup, and what the
post-scan verdict says. Each was discovered against the live API and each is easy
to get subtly wrong (the snap copy and the pool's own primary copy both look
plausible and are both wrong), so they're pinned here.

Note what these DON'T import: `resops.operator.op` reads config/workshop.yaml at
import time, and that file is gitignored – so a test that imported it would pass
on the author's machine and fail on a fresh clone. The parsers live in the read
layer precisely so this suite runs anywhere.
"""
from resops.reads import default_copy_id, storage_pool_id, threat_attestation


# --------------------------------------------------------------------------- #
# storage_pool_id – the id hides under storagePoolEntity, not at the top level.
# --------------------------------------------------------------------------- #
POOLS = {"storagePoolList": [
    {"storagePoolEntity": {"storagePoolName": "Other-Pool", "storagePoolId": 1111}},
    {"storagePoolEntity": {"storagePoolName": "ResOps-Workshop-AirGapProtect",
                           "storagePoolId": 6697}},
]}


def test_storage_pool_id_resolves_by_name():
    assert storage_pool_id(POOLS, "ResOps-Workshop-AirGapProtect") == 6697


def test_storage_pool_id_is_none_when_absent():
    # None, not an exception – the write lane turns it into a SystemExit with the fix.
    assert storage_pool_id(POOLS, "no-such-pool") is None


def test_storage_pool_id_survives_an_empty_response():
    assert storage_pool_id({}, "anything") is None


# --------------------------------------------------------------------------- #
# default_copy_id – the snap copy is a decoy. Scanning it is not scanning the backup.
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
# threat_attestation – the function that exists because we got this wrong.
#
# Client/Anomaly reports EXCEPTIONS. For a month we read "not in the list" as
# "scanned and clean". On 2026-08-01 a live run showed every scan in the tenant
# had analyzed ZERO files, so every clean verdict was hollow. This lane can now
# only ever report a negative it actually saw; a positive must come from an
# attester that knows a check really ran.
# --------------------------------------------------------------------------- #
def test_absence_attests_NOTHING_not_cleanliness():
    # The whole point. No record means nobody checked, not "it's fine".
    assert threat_attestation({"anomalyClients": []}, 12345) is None


def test_zero_counts_attest_nothing():
    # Listed with zeroes is still not proof a scan examined anything.
    body = {"anomalyClients": [{"client": {"clientId": 12345},
                                "infectedFilesCount": 0, "fingerPrintFilesCount": 0}]}
    assert threat_attestation(body, 12345) is None


def test_infected_files_are_a_real_negative():
    body = {"anomalyClients": [{"client": {"clientId": 12345},
                                "infectedFilesCount": 3, "fingerPrintFilesCount": 0}]}
    att = threat_attestation(body, 12345)
    assert att["clean"] is False
    assert att["source"] == "threatscan"
    assert "3 infected" in att["detail"]


def test_fingerprint_anomalies_alone_are_a_real_negative():
    # Mass encryption fires the file-anomaly signal with zero malware matches.
    body = {"anomalyClients": [{"client": {"clientId": 12345},
                                "infectedFilesCount": 0, "fingerPrintFilesCount": 42}]}
    assert threat_attestation(body, 12345)["clean"] is False


def test_an_unrecognized_shape_fails_closed():
    # Flagged by the API in a shape we can't parse. Not clean, and say why.
    body = {"anomalyClients": [{"client": {"clientId": 12345},
                                "someFutureFieldName": 7}]}
    att = threat_attestation(body, 12345)
    assert att["clean"] is False
    assert "don't" in att["detail"] or "recognize" in att["detail"]


# The VSA payload below is VERBATIM from GET Client/Anomaly on 2026-08-12, the first
# time this project ever observed a real detection: two EICAR files were planted in
# aug12-narwhal, backed up, and threat-scanned. Until that day the dirty shape had
# never been seen, the parser did not know this key, and the fail-closed guard was
# the only thing standing between us and a false CLEAN. Do not "simplify" these.
def _vsa(count):
    return {"anomalyClients": [{"client": {"clientId": 12345},
                                "anomalyType": 8192, "appType": 106,
                                "vsaSecurityScanAnomalyInfo": {"malwareItemsCount": count}}]}


def test_vsa_malware_count_is_a_real_negative():
    att = threat_attestation(_vsa(2), 12345)
    assert att["clean"] is False
    assert att["malwareItemsCount"] == 2
    assert "2 malware" in att["detail"]


def test_vsa_zero_malware_attests_NOTHING():
    """Listed by the scan with a zero count means it recorded no malware. That is
    NOT "scanned and clean" – it is the absence this whole module exists to refuse
    to over-read. orders-api and cherry-turtles were both live examples on the day."""
    assert threat_attestation(_vsa(0), 12345) is None


def test_vsa_shape_does_not_swallow_the_fail_closed_guard():
    """A VSA record whose count is missing or non-numeric must still fail closed
    rather than fall through to a None that reads as "nothing to report"."""
    body = {"anomalyClients": [{"client": {"clientId": 12345},
                                "vsaSecurityScanAnomalyInfo": {"somethingElse": 1}}]}
    assert threat_attestation(body, 12345)["clean"] is False


def test_another_clients_anomalies_do_not_taint_ours():
    body = {"anomalyClients": [{"client": {"clientId": 99999},
                                "infectedFilesCount": 500, "fingerPrintFilesCount": 500}]}
    assert threat_attestation(body, 12345) is None
