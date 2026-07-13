"""
Control crosswalk resolver — joins our capabilities to selected framework packs.

The join is the whole design: CAPABILITIES (code) x framework packs (data) ->
a resolved control map the bundle carries. Pick regimes in config:

    frameworks: [dora, nist-800-53, apra-cps230]

Adding a regime is a YAML file in config/frameworks/ + its id here. No code change.
Indicative mapping only — it supports a resilience programme, never an attestation.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .capabilities import CAPABILITIES

ROOT = Path(__file__).resolve().parents[2]   # resops/assurance/ -> repo root
FRAMEWORKS_DIR = ROOT / "config" / "frameworks"


def load_framework(framework_id: str) -> dict:
    """Read one framework pack. Fails loud on an unknown id (boring + predictable)."""
    path = FRAMEWORKS_DIR / f"{framework_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"unknown framework '{framework_id}' — expected {path.relative_to(ROOT)}")
    return yaml.safe_load(path.read_text()) or {}


def resolve_controls(framework_ids: list) -> dict | None:
    """Join capabilities x selected frameworks. None if no frameworks selected."""
    if not framework_ids:
        return None
    packs = [load_framework(fid) for fid in framework_ids]

    controls, crosswalk = {}, {}
    for function, caps in CAPABILITIES.items():
        entries = []
        for cap in caps:
            refs = {p["id"]: p["references"][cap["id"]]
                    for p in packs if cap["id"] in p.get("references", {})}
            entry = {"id": cap["id"], "evidences": cap["evidences"], "references": refs}
            entries.append(entry)
            crosswalk[cap["id"]] = {"evidences": cap["evidences"], "references": refs}
        controls[function] = entries

    frameworks = [{"id": p["id"], "name": p["name"], "disclaimer": p.get("disclaimer", "")}
                  for p in packs]
    names = ", ".join(p["name"] for p in packs)
    disclaimer = (f"Indicative mapping across {names} — supports an internal "
                  "resilience programme, not a compliance attestation.")
    return {"frameworks": frameworks, "disclaimer": disclaimer,
            "controls": controls, "crosswalk": crosswalk}


def load_controls(config: dict) -> dict | None:
    """Resolve the control map for the frameworks named under `gate:` in config
    (or the legacy top-level `frameworks:`), or None."""
    gate = config.get("gate") or {}
    return resolve_controls(gate.get("frameworks") or config.get("frameworks", []))
