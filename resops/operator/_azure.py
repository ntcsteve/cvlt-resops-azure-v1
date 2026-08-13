"""
Azure CLI helpers — the ONE place a subprocess `az` call lives. Shared by the
operator preflight, the restore drill, and teardown so the wrappers (and the
vCPU math that bit us on a 4/4 quota) don't drift between lanes.
"""
from __future__ import annotations

import json
import subprocess

AZ_TIMEOUT = 120


def az_json(*args: str, timeout: int = AZ_TIMEOUT):
    """Run an `az` command, return parsed JSON (or None on failure).

    `timeout` is a keyword because one caller genuinely needs longer: `az vm
    run-command invoke` waits on the guest agent inside the VM, which is slower
    and less predictable than a control-plane call."""
    r = subprocess.run(["az", *args, "-o", "json"], capture_output=True, text=True, timeout=timeout)
    return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None


def az_json_checked(*args: str, timeout: int = AZ_TIMEOUT):
    """Like az_json, but tells "it is not there" apart from "I could not ask".

    az_json() returns None for BOTH, and every caller reads None as absence. That
    is how `op teardown` announced "VM not found — nothing to tear down" about a
    VM that was running, returned success, and left an orphan billing quietly
    (observed live 2026-08-13). When the answer decides whether to destroy
    something or to claim a clean sweep, the two must not look alike.

    Returns None ONLY when az answered and the resource genuinely is not there.
    Raises when az itself failed, because an unanswered question is not a no.

    `az` exits non-zero for a missing resource too, so the reason is read from
    stderr rather than the exit code — that string is the only signal it gives.
    """
    r = subprocess.run(["az", *args, "-o", "json"], capture_output=True, text=True, timeout=timeout)
    if r.returncode == 0:
        return json.loads(r.stdout) if r.stdout.strip() else None
    if "ResourceNotFound" in r.stderr or "was not found" in r.stderr:
        return None
    raise SystemExit(f"az {' '.join(args)} failed, so we cannot tell whether it "
                     f"exists: {r.stderr.strip()[:200]}")


def az_ok(*args: str) -> bool:
    """Run an `az` command for its side effect; print a one-line result, return ok.
    For mutating calls (delete/create) where the JSON is noise and the print is the
    audit line."""
    r = subprocess.run(["az", *args], capture_output=True, text=True, timeout=AZ_TIMEOUT)
    ok = r.returncode == 0
    detail = "" if ok else f"  ({r.stderr.strip()[:120]})"
    print(f"   {'ok ' if ok else 'ERR'}  az {' '.join(args)}{detail}")
    return ok


def vm_size_cores(location: str, size: str) -> int | None:
    """vCPU count for an Azure VM size — read from Azure, never hardcoded."""
    for s in az_json("vm", "list-sizes", "-l", location) or []:
        if s.get("name") == size:
            return s.get("numberOfCores")
    return None


def regional_cores_free(location: str) -> int | None:
    """Free Total Regional vCPUs in a location, or None if unreadable."""
    data = az_json("vm", "list-usage", "--location", location)
    cores = {u["localName"]: u for u in (data or [])}.get("Total Regional vCPUs")
    return int(cores["limit"]) - int(cores["currentValue"]) if cores else None
