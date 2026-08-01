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
import time
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


VERIFY_SCRIPT = "/opt/app/verify.sh"
ATTESTATIONS = REPO / "evidence" / "attestations"


def parse_verdict(stdout: str) -> tuple[bool | None, str]:
    """The verify.sh output contract, as a pure function. Returns (clean, detail).

    Pinned here (and by tests) because every rule below fails SILENTLY when broken,
    which is the worst possible failure mode for an attester:

      • the FIRST matching line wins and parsing stops — so a verdict message
        wrapped over two lines is truncated mid-sentence into the attestation,
        the gate reason and the evidence bundle. It has happened once already.
      • no recognisable line means UNATTESTED (None), never clean. A script that
        crashed before printing must not read as a pass.
      • the line is authoritative, not the exit code: a shell script has many ways
        to exit non-zero that say nothing about the data.

    The full contract for the people writing these scripts is in VERIFY.md."""
    line = next((l.strip() for l in stdout.splitlines()
                 if l.strip().startswith(("OK:", "FAIL:", "NO VERIFY"))), "")
    if line.startswith("OK:"):
        return True, line[3:].strip()
    if line.startswith("FAIL:"):
        return False, line[5:].strip()
    if line.startswith("NO VERIFY"):
        return None, (f"no verify script at {VERIFY_SCRIPT} — this workload declares "
                      f"no attester (see VERIFY.md)")
    return None, "verify script produced no verdict line"


def verify_recovered(t: dict) -> tuple[bool | None, str]:
    """Run the workload's own verify script INSIDE the restored copy.

    This is the attestation. Not a metadata proxy, not a vendor verdict — the
    recovery point is opened in isolation and its data is read, by a script a
    participant can read in ten seconds.

    THE VERDICT LINE IS AUTHORITATIVE, NOT THE EXIT CODE. We parse the first
    stdout line starting with OK:/FAIL:, because a shell script has many ways to
    exit non-zero that say nothing about the data (a missing binary, a set -e
    trip). A script that exits without printing a verdict is UNATTESTED, which
    blocks — never a pass. The contract is documented in VERIFY.md.

    Returns (clean, detail). clean is None when we could not run the check at
    all, which is NOT the same as passing: no result blocks the Scan rung."""
    print(f"\nAttesting the recovered copy: {VERIFY_SCRIPT} on {t['new_vm']}…")
    result = az_json("vm", "run-command", "invoke",
                     "-g", t["resource_group"], "-n", t["new_vm"],
                     "--command-id", "RunShellScript",
                     "--scripts", f"[ -x {VERIFY_SCRIPT} ] && {VERIFY_SCRIPT} "
                                  f"|| {{ echo 'NO VERIFY SCRIPT'; exit 127; }}")
    if not result:
        return None, "could not run the verify script (guest agent unreachable?)"
    message = "\n".join(m.get("message", "") for m in result.get("value", []))
    stdout = message.split("[stderr]")[0]
    for l in stdout.splitlines():
        if l.strip():
            print("   ", l.strip()[:160])
    return parse_verdict(stdout)


def write_attestation(vm_name: str, clean: bool | None, detail: str, job_id: str) -> Path:
    """Persist the attestation where the read lane can find it.

    The write lane produces this; `resops` consumes it only when a workload's
    config points at it (workload.attestation_file). Explicit, opt-in, and
    absent by default — so a workload with no attester blocks at Scan rather
    than quietly passing."""
    ATTESTATIONS.mkdir(parents=True, exist_ok=True)
    path = ATTESTATIONS / f"{vm_name}.json"
    path.write_text(json.dumps({
        "source": "restore-verify",
        "clean": clean,
        "detail": detail,
        # WHEN matters as much as WHETHER. An attestation from a year ago and one
        # from ten minutes ago are not the same claim, and without this they look
        # identical to the ladder — the same false-clean trap in different clothes.
        # The gate enforces the age bar (tiers.yaml attestation_max_age_days).
        "at": int(time.time()),
        "restore_job": job_id,
        "script": VERIFY_SCRIPT,
    }, indent=2) + "\n")
    return path


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

    # A running VM is not a verified one. Open the recovery point and read it.
    clean, detail = (None, "not attempted — VM never came up healthy")
    if healthy:
        clean, detail = verify_recovered(t)
    path = write_attestation(t["source"], clean, detail, str(job_id))

    verdict = {True: "PASS — attested clean",
               False: "FAIL — attestation failed",
               None: "UNATTESTED — could not verify"}[clean]
    print("\n=== DRILL VERDICT ===")
    print(f"  job status : {status}")
    print(f"  azure VM   : {'PASS — exists & running' if healthy else 'FAIL — not healthy'}")
    print(f"  attestation: {verdict}")
    print(f"               {detail}")
    print(f"               → {path.relative_to(REPO)}")

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

    # A restore that came back compromised is a failed drill, not a passed one.
    if not healthy:
        return 2
    return 0 if clean else 3


if __name__ == "__main__":
    sys.exit(main())
