"""
Config loader – one home for the workshop config. `config/workshop.yaml` is the
single file you fill (workload + platform + gate); this reads the `platform:`
block (live ids) and fails LOUD on a missing file or key, so a typo surfaces HERE
(with the fix), not three API calls deep.

Earns its spot by validating: a workshop attendee gets "workshop.yaml: platform
is missing key 'hypervisor'" instead of a KeyError mid-restore.
"""
from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
DEFAULT = REPO / "config" / "workshop.yaml"
TIERS_PATH = REPO / "config" / "tiers.yaml"

# Keys the PYTHON operator needs from platform:. Terraform-only fields
# (storage_pool_name, commvault_sp_object_id) are validated by Terraform at
# plan time – adding them here would force them on read-only `resops` runs
# that never touch infra. hypervisor must carry id+name+instance_id.
_REQUIRED = ("web_service_url", "subscription_id", "hypervisor", "plan_id")
_HYP_REQUIRED = ("id", "name", "instance_id")


def _platform(path: Path) -> dict:
    return (yaml.safe_load(path.read_text()) or {}).get("platform") or {}


def platform_url(path: Path | None = None) -> str | None:
    """Just the API URL from workshop.yaml's platform block. The read-only lane
    needs only this – not the full write-lane identity – so a plain `resops gate`
    doesn't demand the hypervisor/plan ids it never uses. None if file/key absent.
    """
    p = Path(path) if path else DEFAULT
    if not p.exists():
        return None
    return _platform(p).get("web_service_url")


def load_platform(path: Path | None = None) -> dict:
    """Load + validate the platform block. Raises SystemExit with the fix on any gap."""
    p = Path(path) if path else DEFAULT
    if not p.exists():
        raise SystemExit(f"missing {p.name} – copy config/workshop.yaml.example and fill it in")
    cfg = _platform(p)
    missing = [k for k in _REQUIRED if k not in cfg]
    if missing:
        raise SystemExit(f"{p.name}: platform is missing key(s) {missing}")
    hyp_missing = [k for k in _HYP_REQUIRED if k not in (cfg.get("hypervisor") or {})]
    if hyp_missing:
        raise SystemExit(f"{p.name}: platform.hypervisor is missing {hyp_missing}")
    return cfg


def load_tiers(path: Path | None = None) -> dict:
    """Load tiers.yaml – returns the tiers dict keyed by tier name.
    Returns {} if the file doesn't exist (tiers are optional)."""
    p = Path(path) if path else TIERS_PATH
    if not p.exists():
        return {}
    data = yaml.safe_load(p.read_text()) or {}
    return data.get("tiers", {})
