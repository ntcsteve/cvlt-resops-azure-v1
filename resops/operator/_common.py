"""
Shared operator wiring — auth client, validated platform config, and the
terraform contract reader. Used by op.py and preflight.py (teardown lives in
op.py) so neither re-declares setup. Small on purpose — it earns its spot.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ..client import Client, load_credentials
from ..config import load_platform
from ..client import MAINTENANCE_MSG, is_html_response
from ..reads import vmgroup_name

REPO = Path(__file__).resolve().parents[2]  # resops/operator/_common.py -> repo root

CFG = load_platform()          # validated — fails loud on a missing id
HYP = CFG["hypervisor"]        # {id, name, instance_id}
HOST = CFG["web_service_url"]
client = Client(HOST, load_credentials(REPO / ".env"), REPO / ".env")


def contract(run_dir: str) -> dict:
    """The `workload` terraform output — the only handoff from provision to operate.
    Fails with the fix if the root wasn't applied or doesn't expose `workload`."""
    proc = subprocess.run(["terraform", f"-chdir={run_dir}", "output", "-json", "workload"],
                          capture_output=True, text=True)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise SystemExit(f"no `workload` output in {run_dir} — did you `terraform apply`? "
                         f'(the root must expose: output "workload" {{ value = {{...}} }})')
    return json.loads(proc.stdout)


def write(method: str, path: str, **kwargs):
    """A MUTATING request, with renew-on-401. The resops Client is read-only by
    design (it physically cannot write); the write lane lives here, on the same
    authenticated session, and renews the token if it expired mid-run."""
    url = f"{HOST}/{path}"
    resp = client._session.request(method, url, timeout=60, **kwargs)
    if resp.status_code == 401:
        client.ensure_fresh_token()  # renews + updates the session's bearer token
        resp = client._session.request(method, url, timeout=60, **kwargs)
    # EVERY write call site here either ignores the body or parses it as JSON, and
    # each one guards on `status_code != 200` only. During a maintenance window that
    # guard is useless: GETs come back 200 with an HTML page and POSTs come back 405
    # with one, so callers sailed past and died on .json() with a raw traceback that
    # reads as "the tool is broken" rather than "the vendor is down". Stop here, once.
    # Live on 2026-08-12.
    try:
        resp.json()
    except ValueError:
        why = MAINTENANCE_MSG if is_html_response(resp) \
            else (f"HTTP {resp.status_code} with a body that is not JSON "
                  f"({len(resp.text)} bytes)")
        raise SystemExit(f"{method} {path}: {why}"
                         f"  → wait and retry. Nothing was written.")
    return resp


def discovered(vm_name: str) -> bool:
    """True if the VM is in the cloud-native inventory (discovery has run). This is
    the RELIABLE signal: /VM (VSA) lags and stays empty until protect creates the
    group, so checking it pre-protect gives a false negative. Asset/Search is the
    Resources view — a discovered VM appears here right away (AssetType 1 = VM)."""
    body = {"searchParams": [
        {"key": "q", "value": "*:*"}, {"key": "fq", "value": "Provider:1"},
        {"key": "rows", "value": "500"}, {"key": "fl", "value": "AssetName,AssetType"}]}
    js = write("POST", "Asset/Search", json=body).json()
    docs = js.get("docs") or js.get("response", {}).get("docs") or []
    return any(d.get("AssetName") == vm_name and d.get("AssetType") == 1 for d in docs)


def find_vm(vm_name: str) -> dict | None:
    """The VM's /VM record, or None if discovery hasn't surfaced it yet."""
    for v in client.get("VM").json().get("vmStatusInfoList", []):
        if v.get("name") == vm_name:
            return v
    return None


def group_id(vm_name: str) -> int | None:
    """The workload's vmgroup id, by name. The vmgroups list reflects a new group
    immediately — unlike /VM, which lags for a minute after protect."""
    name = vmgroup_name(vm_name)
    for g in client.get("v4/vmgroups").json().get("vmGroups", []):
        gg = g.get("vmGroup") or {}
        if gg.get("name") == name:
            return gg.get("id")
    return None
