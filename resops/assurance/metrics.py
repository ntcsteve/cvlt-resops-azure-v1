"""
Prometheus exposition — the ladder as metrics, so a fleet fits on one wall.

The question a platform team cannot answer today is not "is payments-api up";
they have that. It is:

    how much of my estate is PROVABLY recoverable?
    which workloads have a stale attestation?
    which controls do I actually have evidence for?

All three are already computed on every run. This module does no judging and no
I/O — it takes the summary + bundles a run already wrote and formats them. Judge
once, publish many.

CARDINALITY IS A DESIGN DECISION. Control coverage is a COUNT keyed by
(framework, control, capability, outcome) — bounded by frameworks x capabilities,
so it stays ~60 series whether you protect 6 workloads or 600. Per-workload
detail lives in resops_workload_info, which is one series per workload. Nothing
here multiplies workloads by capabilities.
"""
from __future__ import annotations

from ..state import State

PREFIX = "resops"


def _escape(value: str) -> str:
    """Prometheus label values escape backslash, quote and newline. Nothing else."""
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _labels(pairs: dict) -> str:
    """Render label pairs, dropping empties so absent data never becomes `""`."""
    inner = ",".join(f'{k}="{_escape(v)}"' for k, v in pairs.items() if v not in (None, ""))
    return "{" + inner + "}" if inner else ""


def _metric(name: str, labels: dict, value) -> str:
    return f"{PREFIX}_{name}{_labels(labels)} {value}"


def _rank(state_name: str) -> int | None:
    """The rung as a number, so Grafana can chart it. None for anything the
    ladder doesn't recognise — better a missing series than a wrong one."""
    member = State.__members__.get(state_name)
    return member.rank if member else None


def control_coverage(bundles: list) -> dict:
    """Count workloads per (framework, control, capability, outcome).

    The crosswalk join already happened during the run — every function in a
    bundle carries its capability and that capability's framework references.
    This only tallies them.

    Expect this to be mostly RED. It measures whether recovery was PROVEN, not
    whether a policy exists, and that is the entire point: a compliance view that
    is green without work would be theatre."""
    tally: dict = {}
    for bundle in bundles:
        for function in bundle.get("functions", []):
            outcome = function.get("outcome", "")
            for capability in function.get("controls", []) or []:
                cap_id = capability.get("id", "")
                for framework, reference in (capability.get("references") or {}).items():
                    key = (framework, reference, cap_id, outcome)
                    tally[key] = tally.get(key, 0) + 1
    return tally


def render_metrics(summary: dict, bundles: list) -> str:
    """The whole exposition, as text. Pure — no clock, no files, no network."""
    lines: list[str] = []
    workloads = summary.get("workloads", [])

    lines += [
        f"# HELP {PREFIX}_rung Readiness ladder rung (0 UNDISCOVERED .. 6 VALIDATED).",
        f"# TYPE {PREFIX}_rung gauge",
    ]
    for w in workloads:
        rank = _rank(w.get("state", ""))
        if rank is not None:
            lines.append(_metric("rung", {
                "workload": w.get("name"), "env": w.get("env"),
                "owner": w.get("owner"), "criticality": w.get("criticality"),
            }, rank))

    lines += [
        "",
        f"# HELP {PREFIX}_promotable 1 if the gate would PROMOTE this workload, else 0.",
        f"# TYPE {PREFIX}_promotable gauge",
    ]
    for w in workloads:
        gate = w.get("gate")
        if gate:
            lines.append(_metric("promotable", {"workload": w.get("name")},
                                 1 if gate in ("PROMOTE", "OVERRIDE") else 0))

    lines += [
        "",
        f"# HELP {PREFIX}_tolerated 1 if this workload has a live enforcement "
        f"tolerance (declared, dated, excluded from the aggregate until it expires).",
        f"# TYPE {PREFIX}_tolerated gauge",
    ]
    # Emitted for every workload, 0 included: this is the number that has to go
    # DOWN, and a series that only appears when someone opts out cannot be trended.
    for w in workloads:
        lines.append(_metric("tolerated", {"workload": w.get("name")},
                             1 if w.get("tolerated") else 0))

    lines += [
        "",
        f"# HELP {PREFIX}_attestation_age_days Days since anything verified the "
        f"recovery point. Absent means nothing ever has.",
        f"# TYPE {PREFIX}_attestation_age_days gauge",
    ]
    for w in workloads:
        age = w.get("attestation_age_days")
        if age is not None:
            lines.append(_metric("attestation_age_days", {"workload": w.get("name")}, age))

    lines += [
        "",
        f"# HELP {PREFIX}_workload_info Always 1. The labels carry the detail: "
        f"which rung, which stage is blocking, what the gate said.",
        f"# TYPE {PREFIX}_workload_info gauge",
    ]
    for w in workloads:
        lines.append(_metric("workload_info", {
            "workload": w.get("name"), "state": w.get("state"),
            "blocked_stage": w.get("blocked_stage"), "gate": w.get("gate"),
            "env": w.get("env"), "owner": w.get("owner"),
            # Absent unless declared — _labels() drops empties, so an estate with
            # no tolerances carries no extra label and no extra cardinality.
            "enforce_from": w.get("enforce_from"),
        }, 1))

    tally = control_coverage(bundles)
    lines += [
        "",
        f"# HELP {PREFIX}_control_coverage Workloads per control per outcome. "
        f"INDICATIVE mapping — supports a resilience programme, not an attestation.",
        f"# TYPE {PREFIX}_control_coverage gauge",
    ]
    for (framework, control, capability, outcome), count in sorted(tally.items()):
        lines.append(_metric("control_coverage", {
            "framework": framework, "control": control,
            "capability": capability, "outcome": outcome,
        }, count))

    lines += [
        "",
        f"# HELP {PREFIX}_workloads_total Workloads evaluated in this run.",
        f"# TYPE {PREFIX}_workloads_total gauge",
        _metric("workloads_total", {}, len(workloads)),
    ]
    return "\n".join(lines) + "\n"
