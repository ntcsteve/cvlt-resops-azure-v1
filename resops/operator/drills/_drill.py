"""
Shared toolkit for the MUTATING drill lane – Azure CLI, Commvault auth, and
restore-payload parsing. Kept apart from the read-only `resops` package on
purpose: nothing here belongs in the safe loop.
"""
from __future__ import annotations

import json
from pathlib import Path

import requests

from ...client import USER_AGENT, Client, load_credentials
# The az + vCPU helpers live in one place (resops/_azure.py) shared with preflight.
# Re-exported here as the drill lane's facade; `az` is the printing side-effect form.
from .._azure import az_json, az_json_checked, regional_cores_free, vm_size_cores
from .._azure import az_ok as az  # noqa: F401  (drill calls `az(...)` for side effects)


# --------------------------------------------------------------------------- #
# Restore payload  (env-specific; `op restore` derives it and writes it here)
# --------------------------------------------------------------------------- #
def load_restore_payload(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(
            f"Missing {path.name}. `op restore` derives this payload and writes it here "
            f"before running the drill – run `op restore <run_dir>`. See the README."
        )
    return json.loads(path.read_text())


def restore_target(payload: dict) -> dict:
    """The human-meaningful restore fields, pulled out of a CreateTask payload."""
    adv = (payload["taskInfo"]["subTasks"][0]["options"]["restoreOptions"]
           ["virtualServerRstOption"]["diskLevelVMRestoreOption"]["advancedRestoreOptions"][0])
    return {
        "source": adv["name"],
        "new_vm": adv["newName"],
        "resource_group": adv["esxHost"],
        "location": adv["datacenter"],
        "vm_size": adv["vmSize"],
    }


# --------------------------------------------------------------------------- #
# Commvault auth for the mutating POST
# --------------------------------------------------------------------------- #
def bearer_session(token: str) -> requests.Session:
    """A requests.Session carrying a Commvault bearer token, for the restore POST
    (the read-only Client deliberately won't make non-GET calls)."""
    session = requests.Session()
    session.headers.update({
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "Authorization": f"Bearer {token}",
    })
    return session


def authed_client(host: str, env_path: Path) -> Client:
    """A read-only Client with a freshly-renewed token – used to poll the job
    and to mint a current bearer token for the POST."""
    client = Client(host, load_credentials(env_path), env_path)
    client.ensure_fresh_token()
    return client
