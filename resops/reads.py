"""
The read layer — every read-only GET we make, and the small pure parsers over
the responses. gather() (state.py) composes these into a Reads; classify() then
decides. They only ever read the solid token-native lane and never raise: a
broken read returns ({}, error) / (None, error), which becomes a block on the
matching rung, never a crash.
"""
from __future__ import annotations

import json
import time

import requests

from .client import Client

SUMMARY_CLIP = 80        # max chars of verbose API error text in a one-line summary
MAX_RESTORE_SCAN = 10    # how many recent restore jobs we inspect for recovery proof


def _get(client: Client, path: str) -> tuple[dict, str]:
    """Return (json_dict, error). error is '' on success."""
    try:
        resp = client.get(path)
    except requests.RequestException as err:
        return {}, str(err)
    if resp.status_code != 200:
        return {}, f"HTTP {resp.status_code}"
    try:
        body = resp.json()
    except ValueError:
        return {}, "non-JSON response"
    return (body if isinstance(body, dict) else {}), ""


def list_vmgroups(client: Client) -> tuple[list, str]:
    """All VM groups with their coverage counts — the onboarding lookup so a new
    user can find their vm_group_id. Returns (vmGroups, error). NOTE: the list
    endpoint is lowercase+plural (`v4/vmgroups`); the singular `V4/VMGroup/{id}`
    404s on the list — casing bit us once, so it's pinned here."""
    body, err = _get(client, "v4/vmgroups")
    if err:
        return [], err
    return body.get("vmGroups", []), ""


def vmgroup_name(name: str) -> str:
    """The VM group name for a workload — the ONE naming convention, shared by the
    write lane (op.protect creates it) and the read lane (resolve it). Lives here,
    in the read-only layer both depend on, so the convention can't drift."""
    return f"resops-{name}-vg"


def find_vmgroup_id(client: Client, name: str) -> tuple[int | None, str]:
    """Resolve a workload's vm group id by its name (resops-<name>-vg) — so the
    workshop declares only `name`, never a hand-copied runtime id. Returns
    (id, error); id is None if no group matches (i.e. not protected yet)."""
    groups, err = list_vmgroups(client)
    if err:
        return None, err
    wanted = vmgroup_name(name)
    for g in groups:
        gg = g.get("vmGroup") or {}
        if gg.get("name") == wanted:
            return gg.get("id"), ""
    return None, ""


def _recovery_proof(client: Client, vm_name: str) -> tuple[dict | None, str]:
    """Latest restore job that involved this VM. Returns (jobSummary, error);
    jobSummary is None if no restore on record. Restore jobs are excluded from
    the default /Job list, so we ask for them explicitly, then confirm each one
    references our source VM via job detail."""
    body, err = _get(client, "Job?jobFilter=Restore")
    if err:
        return None, err
    jobs = sorted(body.get("jobs", []),
                  key=lambda j: j.get("jobSummary", {}).get("jobId", 0), reverse=True)
    for job in jobs[:MAX_RESTORE_SCAN]:
        summary = job.get("jobSummary", {})
        detail, derr = _get(client, f"Job/{summary.get('jobId')}")
        if derr:
            continue
        # String search across the full JSON — works because the VM name appears
        # in a known source field, but could false-match a substring in log/comment
        # fields. Rebuild as a structured field check when the API shape is pinned.
        if vm_name and vm_name in json.dumps(detail):
            return summary, ""
    return None, ""


def _age_days(job_summary: dict) -> float | None:
    for key in ("jobEndTime", "jobStartTime", "lastUpdateTime"):
        t = job_summary.get(key)
        if t:
            return round((time.time() - t) / 86400, 1)
    return None


def _rpo_hours(vm: dict | None) -> float | None:
    """Hours since the VM's last successful backup — the RPO age. Reads the clock,
    so it lives here at the I/O edge, not in the pure classify()."""
    last = (vm or {}).get("lastSuccessfulBackupTime")
    return round((time.time() - last) / 3600, 1) if last else None


def _rto_minutes(job_summary: dict) -> float | None:
    """Restore-job duration (end - start) in minutes. A measured proxy for RTO —
    recovery-EXECUTION time, not full business RTO (no detect/decide/service-up)."""
    start, end = job_summary.get("jobStartTime"), job_summary.get("jobEndTime")
    if start and end and end >= start:
        return round((end - start) / 60, 1)
    return None


def _find_vm(client: Client, vm_name: str) -> tuple[dict | None, str]:
    """Find one VM's per-record in GET /VM by name. Returns (vm, error);
    vm is None if not found."""
    body, err = _get(client, "VM")
    if err:
        return None, err
    for vm in body.get("vmStatusInfoList", []):
        if vm.get("name") == vm_name:
            return vm, ""
    return None, ""


def _plan_name(vmgroup_body: dict) -> str:
    return (vmgroup_body.get("summary", {}).get("plan") or {}).get("name", "")


# --------------------------------------------------------------------------- #
# Threat-scan parsers. Pure, like everything else here: they take an already-
# fetched body and return a value or None — never raise, never exit. They live in
# the read layer (not the operator) for two reasons: the responses they parse are
# plain reads, and importing `resops.operator` requires a filled config/workshop.yaml
# (gitignored), which would make these untestable on a fresh clone. The write lane
# imports them and owns the "stop with the fix" behaviour on a None.
# --------------------------------------------------------------------------- #
def storage_pool_id(body: dict, pool_name: str) -> int | None:
    """storagePoolId for a pool NAME. The id lives one level down, under
    storagePoolEntity — the list itself carries no flat id."""
    for pool in body.get("storagePoolList", []):
        entity = pool.get("storagePoolEntity") or {}
        if entity.get("storagePoolName") == pool_name:
            return entity.get("storagePoolId")
    return None


def default_copy_id(body: dict) -> int | None:
    """The copy that actually holds backed-up data: the policy's isDefault copy.
    A policy also carries a snap copy, which points at the same pool but expires
    on its own faster schedule — scanning it is not the same as scanning the
    backup. Confirmed live: the PLAN's policy is the one our jobs write to, not
    the storage pool's own primary copy, which is a different object entirely."""
    for copy in body.get("copy", []):
        if copy.get("isDefault"):
            return (copy.get("StoragePolicyCopy") or {}).get("copyId")
    return None


ANOMALY_COUNTS = ("infectedFilesCount", "fingerPrintFilesCount")


def threat_attestation(body: dict, commcell_client_id: int) -> dict | None:
    """An ATTESTATION about a recovery point, derived from GET Client/Anomaly.

    Returns None when there is nothing to attest — which is the honest answer
    far more often than it looks.

    THE MISTAKE THIS FUNCTION EXISTS TO PREVENT. Client/Anomaly reports
    EXCEPTIONS. A client absent from that list has no *recorded anomaly*, which
    is NOT the same as "was scanned and found clean". We read absence as an
    all-clear for a month; the live run on 2026-08-01 showed every scan in this
    tenant had analysed zero files, so the clean verdicts meant nothing at all.
    Absence of evidence is not evidence of absence, and a recoverability tool
    that confuses the two is worse than no tool.

    So this only ever reports a NEGATIVE it can actually see:
        anomalies recorded   -> attested, clean=False
        anything else        -> None, i.e. nobody has attested anything

    A positive attestation has to come from a source that knows a check really
    ran — see the metadata attester (integrity_attestation)."""
    for entry in body.get("anomalyClients", []):
        if (entry.get("client") or {}).get("clientId") != commcell_client_id:
            continue
        if not any(key in entry for key in ANOMALY_COUNTS):
            return {"source": "threatscan", "clean": False,
                    "detail": "listed as an anomaly client in a shape we don't "
                              "recognise — treating as NOT clean"}
        infected = entry.get("infectedFilesCount", 0) or 0
        fingerprint = entry.get("fingerPrintFilesCount", 0) or 0
        if not (infected or fingerprint):
            return None          # listed but with zero counts — attests nothing
        return {"source": "threatscan", "clean": False,
                "detail": f"{infected} infected, {fingerprint} file-anomaly",
                "infectedFilesCount": infected, "fingerPrintFilesCount": fingerprint}
    return None


def _vms_in_group(vmgroup_body: dict) -> list:
    """VM names declared in a VM group's content."""
    names = []
    for entry in (vmgroup_body.get("content") or []):
        names += [vm.get("name") for vm in entry.get("virtualMachines", [])]
    return names
