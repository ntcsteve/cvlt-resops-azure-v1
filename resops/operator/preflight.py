"""
preflight — the read-only gate. Refuses to let a lane act until the world is
sane. Each check returns (ok, message); a failure carries its own FIX. Any FAIL
stops the run (exit 1). This is where the surprises that used to bite mid-run
(expired token, quota 4/4, skipped discovery) get caught up front, cheaply.

Run standalone:  python3 -m resops.operator.preflight <run_dir>
Wired into:      op climb  (runs before protect)
"""
import sys

import requests

from ._azure import az_json, regional_cores_free, vm_size_cores
from ..reads import MAINTENANCE_MSG, is_html_body
from ._common import CFG, HYP, client, contract, discovered


# --------------------------------------------------------------------------- #
# checks — each returns (ok: bool, message: str). message ends with the fix on FAIL.
# --------------------------------------------------------------------------- #
def check_az() -> tuple:
    acct = az_json("account", "show")
    if not acct:
        return False, "az not logged in  → fix: az login"
    if acct.get("id") != CFG["subscription_id"]:
        return False, (f"az on wrong subscription ({acct.get('id', '')[:8]}…)  "
                       f"→ fix: az account set --subscription {CFG['subscription_id']}")
    return True, "az logged in, correct subscription"


def check_token() -> tuple:
    try:
        resp = client.get("VM")
    except requests.RequestException as e:
        return False, f"Commvault read failed ({e})  → fix: python3 -m resops list"
    # 200 alone is not proof the API is up: a tenant in maintenance answers every
    # route with 200 and an HTML page, and this check used to report "token valid"
    # straight through an outage. Live on 2026-08-12.
    if is_html_body(resp.headers.get("content-type", ""), resp.text):
        return False, f"{MAINTENANCE_MSG}  → wait for the window to clear"
    if resp.status_code != 200:
        return False, "Commvault read != 200  → fix: python3 -m resops list"
    return True, "Commvault token valid"


def check_hypervisor() -> tuple:
    r = client.get(f"V4/Hypervisor/{HYP['id']}")
    if r.status_code != 200:
        return False, f"hypervisor {HYP['id']} unreadable (HTTP {r.status_code})  → fix: config/workshop.yaml platform.hypervisor.id"
    return True, f"hypervisor {HYP['id']} ({HYP['name']}) reachable"


def check_discovered(vm_name: str) -> tuple:
    return (True, f"{vm_name} discovered (cloud-native inventory)") if discovered(vm_name) else \
        (False, f"{vm_name} not discovered  → fix: run discovery in the UI (the one gated step)")


def check_vcpu(loc: str, size: str) -> tuple:
    need, free = vm_size_cores(loc, size), regional_cores_free(loc)
    if need is None or free is None:
        return True, "vCPU check skipped (az unavailable)"
    return (True, f"vCPU: {free} free in {loc} >= {need} (restore VM)") if free >= need else \
        (False, f"vCPU: only {free} free in {loc}, restore needs {need}  → fix: free a VM or raise quota")


# --------------------------------------------------------------------------- #
def run(run_dir: str) -> None:
    w = contract(run_dir)
    checks = [
        check_az(), check_token(), check_hypervisor(),
        check_discovered(w["vm_name"]), check_vcpu(w["location"], w["vm_size"]),
    ]
    all_ok = True
    for ok, msg in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {msg}")
        all_ok = all_ok and ok
    if not all_ok:
        sys.exit("preflight FAILED — fix the above, then retry")
    print("preflight PASS — safe to climb")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m resops.operator.preflight <run_dir>")
    client.ensure_fresh_token()
    run(sys.argv[1])
