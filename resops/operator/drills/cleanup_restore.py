#!/usr/bin/env python3
"""
Tear down a restored Azure VM and the disk / NIC / public-IP it created — so a
recovery drill never leaves infra (or cost) behind.

Captures the VM's attached resources first, then deletes VM → NIC → public-IP →
OS disk. Targets are derived from the restore payload; nothing is hardcoded.

Usage:  python3 -m resops.operator.drills.cleanup_restore [vm_name]   (default: the restore's newName)
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

from ._drill import az, az_json, az_json_checked, load_restore_payload, restore_target


def teardown_vm(resource_group: str, vm_name: str) -> bool:
    """Delete a VM and the dedicated disk/NIC/public-IP it owns. Idempotent."""
    # az_json_checked, NOT az_json: the plain one returns None both when the VM is
    # absent and when the `az` call failed, and this branch turns None into "nothing
    # to do" plus a success return. On 2026-08-13 that announced a clean teardown
    # over a VM, NIC and disk that were all still running and billing. A lookup we
    # could not make is not an absence, so it raises instead.
    vm = az_json_checked("vm", "show", "-g", resource_group, "-n", vm_name)
    if not vm:
        print(f"VM {vm_name} not found in {resource_group} — nothing to tear down.")
        return True

    os_disk = vm["storageProfile"]["osDisk"]["managedDisk"]["id"]
    nic_ids = [nic["id"] for nic in vm["networkProfile"]["networkInterfaces"]]
    public_ip_ids = [
        ip["publicIPAddress"]["id"]
        for nic_id in nic_ids
        for ip in (az_json("network", "nic", "show", "--ids", nic_id) or {}).get("ipConfigurations", [])
        if ip.get("publicIPAddress")
    ]

    print(f"Tearing down {vm_name}: VM + OS disk + {len(nic_ids)} NIC + {len(public_ip_ids)} public-IP")
    az("vm", "delete", "-g", resource_group, "-n", vm_name, "--yes")
    for nic_id in nic_ids:
        az("network", "nic", "delete", "--ids", nic_id)
    for ip_id in public_ip_ids:
        az("network", "public-ip", "delete", "--ids", ip_id)
    az("disk", "delete", "--ids", os_disk, "--yes")
    print("Teardown complete.")
    return True


if __name__ == "__main__":
    target = restore_target(load_restore_payload(HERE / "restore_headless.json"))
    vm_name = sys.argv[1] if len(sys.argv) > 1 else target["new_vm"]
    teardown_vm(target["resource_group"], vm_name)
