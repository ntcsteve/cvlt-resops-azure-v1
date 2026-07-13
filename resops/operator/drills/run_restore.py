#!/usr/bin/env python3
"""
Headless VM restore DRILL — submit, poll, validate in Azure, optionally clean up.

NOT part of the read-only resops loop. Creates a REAL Azure VM. Full cycle:
  1. pre-flight Azure vCPU quota (the first attempt failed VM-create on a 409)
  2. refresh the Commvault token (the POST won't auto-renew)
  3. POST /CreateTask -> restore job
  4. poll the job to a terminal state
  5. validate the VM actually exists and runs in Azure (az vm show)
  6. verdict; on failure, dump the Commvault job events for the reason
  7. --cleanup: tear the VM down afterwards so a drill leaves nothing behind

Run:  python3 -m resops.operator.drills.run_restore [--cleanup]
`op restore` writes the derived payload to PAYLOAD_PATH, then calls main(["--cleanup"]).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from ...config import platform_url
from ..commvault import poll_job
from ._drill import (authed_client, az_json, bearer_session, load_restore_payload,
                     regional_cores_free, restore_target, vm_size_cores)
from .cleanup_restore import teardown_vm

REPO = Path(__file__).resolve().parents[3]            # resops/operator/drills/ -> repo root
PAYLOAD_PATH = Path(__file__).resolve().parent / "restore_headless.json"


def cores_ok(t: dict) -> bool:
    need = vm_size_cores(t["location"], t["vm_size"])
    free = regional_cores_free(t["location"])
    if need is None or free is None:
        print("  (capacity pre-flight skipped — az unavailable) — proceeding"); return True
    print(f"  Azure vCPUs: {free} free in {t['location']}, {t['vm_size']} needs {need}")
    if free < need:
        print("  ✗ insufficient cores — free a VM or raise quota."); return False
    return True


def dump_events(client, job_id: str) -> None:
    for event in client.get(f"Events?jobId={job_id}").json().get("commservEvents", []):
        msg = (event.get("description") or "").replace("\n", " ").strip()
        if any(k in msg.lower() for k in ("error", "fail", "warn", "unable")):
            print("   •", msg[:400])


def validate_azure(t: dict) -> bool:
    print(f"\nValidating in Azure: {t['new_vm']}…")
    vm = az_json("vm", "show", "-g", t["resource_group"], "-n", t["new_vm"], "--show-details")
    if not vm:
        print("  ✗ VM not found in Azure"); return False
    prov, power = vm.get("provisioningState"), vm.get("powerState")
    print(f"  provisioning: {prov} | power: {power} | "
          f"{vm.get('hardwareProfile', {}).get('vmSize')} / {vm.get('location')} | IP {vm.get('publicIps') or '-'}")
    healthy = prov == "Succeeded" and power == "VM running"
    print(f"  → {'✓ VM exists and is running' if healthy else '✗ VM not in a healthy running state'}")
    return healthy


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    host = (platform_url() or "").rstrip("/")          # the API URL — single source (config/workshop.yaml)
    payload = load_restore_payload(PAYLOAD_PATH)
    t = restore_target(payload)

    print(f"DRILL: restore {t['source']} → {t['new_vm']} "
          f"({t['location']}, {t['vm_size']}) into {t['resource_group']}\n")

    print("Pre-flight: Azure capacity")
    if not cores_ok(t):
        return 1

    print("Pre-flight: refresh Commvault token")
    client = authed_client(host, REPO / ".env")
    print("  token ready")

    resp = bearer_session(client.access_token).post(f"{host}/CreateTask", data=json.dumps(payload), timeout=60)
    print(f"\nPOST /CreateTask → HTTP {resp.status_code}: {resp.text[:200]}")
    if resp.status_code != 200:
        return 1
    job_id = (resp.json().get("jobIds") or [None])[0]
    if not job_id:
        print("  no job id in response — nothing to poll"); return 1

    status = poll_job(client, job_id, timeout=540)
    print(f"\nJob {job_id} terminal status: {status!r}")
    if status == "TIMEOUT" or "Failed" in status or "Killed" in status:
        print("Commvault reported a problem — events:")
        dump_events(client, job_id)

    healthy = validate_azure(t)
    if not healthy:
        print("\nCommvault job events (why the VM isn't healthy):")
        dump_events(client, job_id)

    print("\n=== DRILL VERDICT ===")
    print(f"  job status : {status}")
    print(f"  azure VM   : {'PASS — exists & running' if healthy else 'FAIL — not healthy'}")

    # Opt-in self-teardown so a repeatable drill never leaves infra behind.
    if "--cleanup" in argv and healthy:
        # Workshop UX: in an interactive terminal, let the user SEE the recovered
        # VM (connect, check the data) before it's torn down — the "aha" moment.
        # Headless/CI (no tty) skips the pause so automation stays unattended.
        if sys.stdin.isatty() and "--no-pause" not in argv:
            print(f"\n  ✓ RECOVERED: {t['new_vm']} is running in Azure (RG {t['resource_group']}).")
            input("    Go look / connect, then press Enter to tear it down… ")
        print("\n--cleanup: tearing down the restored VM…")
        teardown_vm(t["resource_group"], t["new_vm"])

    return 0 if healthy else 2


if __name__ == "__main__":
    sys.exit(main())
