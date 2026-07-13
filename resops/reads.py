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


def _vms_in_group(vmgroup_body: dict) -> list:
    """VM names declared in a VM group's content."""
    names = []
    for entry in (vmgroup_body.get("content") or []):
        names += [vm.get("name") for vm in entry.get("virtualMachines", [])]
    return names
