"""
Rendered report (Tier 1, item T1-3).

Auditors read reports, not bundle.json. This turns a Bundle dict into a human
`report.md` with per-finding RISK RATINGS and the controls each finding
evidences — the requirement->control->evidence chain in readable form.

Risk ratings are a judgement call and an over-statement is a credibility cost,
so the scale is deliberately conservative and documented inline.
"""
from __future__ import annotations

from pathlib import Path

# recover/validate are recovery-critical; a FAIL/GAP there outranks elsewhere.
RECOVERY_CRITICAL = ("recover", "validate")


def risk_rating(function: str, outcome: str) -> str:
    """Map an outcome to a conservative risk rating shown in the report."""
    if outcome in ("PASS", "SKIP"):
        return "none"
    critical = function in RECOVERY_CRITICAL
    if outcome == "FAIL":
        return "high" if critical else "medium"
    if outcome == "GAP":
        return "medium" if critical else "low"
    return "unknown"


def _control_ids(entry: dict) -> str:
    return ", ".join(c.get("id", "") for c in entry.get("controls", [])) or "—"


def render_markdown(bundle: dict) -> str:
    """Render a Bundle dict to an auditor-facing markdown report."""
    counts = bundle.get("summary", {})
    lines = [
        "# ResOps resilience report",
        "",
        f"- **Run:** {bundle.get('run_at', '?')}",
        f"- **Target:** {bundle.get('target', '?')}",
        f"- **Summary:** {counts.get('pass', 0)} pass · {counts.get('gap', 0)} gap · "
        f"{counts.get('fail', 0)} fail · {counts.get('skip', 0)} skip",
        "",
        "| Function | Outcome | Risk | Controls | Finding |",
        "|---|---|---|---|---|",
    ]
    for fn in bundle.get("functions", []):
        rating = risk_rating(fn["function"], fn["outcome"])
        lines.append(
            f"| {fn['function']} | {fn['outcome']} | {rating} | "
            f"{_control_ids(fn)} | {fn['summary']} |"
        )

    findings = bundle.get("findings")
    if findings:
        opens = [f for f in findings if f["status"] == "OPEN"]
        if opens:
            lines += ["", "## Open findings", "",
                      "| Finding | Function | Risk | Runs open | Since |",
                      "|---|---|---|---|---|"]
            for f in opens:
                lines.append(f"| {f['id']} | {f['function']} | {f['risk']} | "
                             f"{f['runs_open']} | {f['since']} |")
        progress = [f for f in findings if f["status"] in ("REMEDIATED", "VERIFIED")]
        if progress:
            lines += ["", "**Remediation progress:** " +
                      "; ".join(f"{f['function']} {f['status'].lower()}" for f in progress)]

    gate = bundle.get("gate")
    if gate:
        reasons = "; ".join(gate.get("reasons", []) or ["recoverability proven"])
        lines += ["", f"**Promotion gate — Continuous Service:** {gate['decision']} — {reasons}"]
        if gate.get("acknowledged_risk"):
            lines.append(f"**Acknowledged risk:** {gate['acknowledged_risk']}")
        # An auditor has to see what the programme chose not to enforce yet, and
        # that the verdict above was NOT softened to accommodate it.
        tolerance = gate.get("tolerance")
        if tolerance:
            when = tolerance.get("enforce_from", "?")
            state = (f"declared, active until {when}" if tolerance.get("active")
                     else f"EXPIRED {when} — now enforced")
            why = f" Reason: {tolerance['reason']}." if tolerance.get("reason") else ""
            lines.append(f"**Enforcement tolerance:** {state}.{why} The verdict above is "
                         f"unchanged; a tolerance only defers whether it blocks promotion.")

    compliance = bundle.get("compliance") or {}
    frameworks = compliance.get("frameworks")
    crosswalk = compliance.get("crosswalk")
    if frameworks and crosswalk:
        fw_ids = [f["id"] for f in frameworks]
        lines += ["", "## Framework references", "",
                  "| Capability | " + " | ".join(fw_ids) + " |",
                  "|---|" + "---|" * len(fw_ids)]
        for cap_id, row in crosswalk.items():
            refs = row.get("references", {})
            cells = " | ".join(refs.get(fid, "—") for fid in fw_ids)
            lines.append(f"| {cap_id} | {cells} |")
    if compliance.get("disclaimer"):
        lines += ["", "---", f"_{compliance['disclaimer']}_"]
    return "\n".join(lines) + "\n"


def write_report(bundle: dict, path: Path) -> None:
    """Write the markdown report beside the evidence bundle."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(bundle))
