"""
Present the readiness ladder for humans — and bridge it to the evidence model.

Two presentation jobs, no decisions:

  ladder_to_results()  folds a Ladder + Trend into the list[FunctionResult] the
                       assurance layer (findings, crosswalk, junit, report,
                       history) already speaks — so none of that had to change
                       when the core became a state machine. The rung→outcome
                       map: cleared→PASS, blocked→GAP (or FAIL if a read error),
                       not-reached→SKIP. Improve rides along from the trend.

  render_headline()    the one-line verdict: the rung bar, the state, the stage
                       you're blocked on, the reason, and the trend arrow.
  render_detail()      the per-stage rows (the old six-row view), behind --detail.
"""
from __future__ import annotations

from .evidence import DEVOPS_LENS, FunctionResult, Outcome
from .state import Ladder, State, Trend

RED, DIM, GREEN, YELLOW, BOLD = "31", "90", "32", "33", "1"


def color(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m"


# --------------------------------------------------------------------------- #
# Bridge: Ladder + Trend -> the FunctionResult list the assurance layer speaks.
# --------------------------------------------------------------------------- #
def ladder_to_results(ladder: Ladder, trend: Trend, metrics: dict | None = None) -> list:
    """Fold the ladder into per-function results. `metrics` (rpo/rto/age, measured
    at the I/O edge) enrich the recover/validate evidence so the bundle, report and
    history carry the numbers classify() leaves out (it's clock-free)."""
    metrics = metrics or {}
    results = []
    for rung in ladder.rungs:
        fn = rung.stage.lower()
        if rung.passed is True:
            outcome = Outcome.PASS
        elif rung.passed is None:
            outcome = Outcome.SKIP
        else:
            outcome = Outcome.FAIL if ladder.blocked_by_error else Outcome.GAP
        summary, evidence = rung.summary, dict(rung.evidence)

        if fn == "recover" and rung.passed and metrics.get("rpo_hours") is not None:
            evidence["rpo_hours"] = metrics["rpo_hours"]
            summary = f"recoverable — RPO {metrics['rpo_hours']}h, SLA Protected"
        if fn == "validate" and rung.passed:
            age, rto = metrics.get("proof_age_days"), metrics.get("rto_minutes")
            if age is not None:
                evidence["drill_age_days"] = age
            if rto is not None:
                evidence["rto_minutes"] = rto
            extra = ([f"{age}d ago"] if age is not None else []) + \
                    ([f"recovery took {rto}m"] if rto is not None else [])
            if extra:
                summary = f"{rung.summary} ({', '.join(extra)})"
        results.append(FunctionResult(fn, outcome, summary, evidence))

    imp = {"regressed": Outcome.GAP, "baseline": Outcome.SKIP}.get(trend.direction, Outcome.PASS)
    results.append(FunctionResult("improve", imp, trend.summary, {
        "direction": trend.direction, "runs": trend.runs,
        "previous": str(trend.previous) if trend.previous else None,
    }))
    return results


# --------------------------------------------------------------------------- #
# Rendering — the headline ladder line and the detail rows.
# --------------------------------------------------------------------------- #
_TREND_TAG = {"climbed": ("↑", GREEN), "held": ("=", DIM),
              "regressed": ("↓", RED), "baseline": ("★", DIM)}


def _state_code(ladder: Ladder) -> str:
    if ladder.state is State.VALIDATED:
        return GREEN
    return RED if ladder.blocked_by_error else YELLOW


def _bar(ladder: Ladder) -> str:
    glyphs = []
    for rung in ladder.rungs:
        if rung.passed is True:
            glyphs.append(color("●", GREEN))
        elif rung.passed is None:
            glyphs.append(color("·", DIM))
        else:
            glyphs.append(color("✗", RED if ladder.blocked_by_error else YELLOW))
    return "".join(glyphs)


def render_headline(name: str, criticality: str, ladder: Ladder,
                    trend: Trend, multi: bool, rpo_hours: float | None = None,
                    env: str = "", owner: str = "") -> list:
    """The verdict in three lines (plus a workload header when multi). RPO age
    rides on the state line when known — the at-a-glance freshness number the
    old recover row used to show (full evidence is in --detail)."""
    lines = []
    if multi:
        tags = "  ".join(t for t in [env, owner] if t and t != "unspecified")
        tag_str = color(f"  {tags}", DIM) if tags else ""
        lines.append(color(f"▸ {name}", BOLD) + tag_str + color(f"  ({criticality})", BOLD))
    state = color(str(ladder.state), _state_code(ladder))
    rpo = color(f"  ·  RPO {rpo_hours}h", DIM) if rpo_hours is not None else ""
    blocked = color(f"  blocked at {ladder.blocked_stage}", DIM) if ladder.blocked_stage else ""
    lines.append(f"  {_bar(ladder)}  {state}{rpo}{blocked}")
    lines.append(color(f"  ↳ {ladder.reason}", DIM))
    sym, code = _TREND_TAG[trend.direction]
    lines.append(color(f"  {sym} {trend.summary}", code))
    return lines


_DETAIL_MARK = {Outcome.PASS: ("✓", GREEN), Outcome.SKIP: ("·", DIM),
                Outcome.GAP: ("✗", YELLOW), Outcome.FAIL: ("✗", RED)}


def render_detail(results: list) -> list:
    """The per-stage rows (the old six-row view), derived from the bridge."""
    lines = []
    for r in results:
        glyph, code = _DETAIL_MARK[r.outcome]
        lines.append(f"      {color(glyph, code)} {r.function:9} {r.summary}")
        lens = DEVOPS_LENS.get(r.function)
        if lens:
            lines.append(color(f"          ↳ {lens}", DIM))
    return lines


def render_vmgroups(vmgroups: list) -> list:
    """The `resops list` table — id, name, coverage — so a new user can read their
    vm_group_id straight off the CLI. Pure: takes the raw vmGroups[]. (No plan
    column: the list endpoint reports coverage but not the attached plan — that
    only shows on the single-group read, surfaced as the Protect rung.)"""
    if not vmgroups:
        return [color("  no VM groups found — check the token's permissions", YELLOW)]
    rows = []
    for item in vmgroups:
        g = item.get("vmGroup", {})
        info = item.get("vmBackupInfo", {})
        rows.append((str(g.get("id", "?")), g.get("name", "?"),
                     f"{info.get('vmProtectedCount', 0)}/{info.get('vmTotalCount', 0)}"))
    id_w = max(len("ID"), *(len(r[0]) for r in rows))
    name_w = max(len("NAME"), *(len(r[1]) for r in rows))
    lines = [color(f"  {'ID':<{id_w}}  {'NAME':<{name_w}}  PROT/TOTAL", DIM)]
    for rid, name, cov in rows:
        lines.append(f"  {rid:<{id_w}}  {name:<{name_w}}  {cov}")
    lines.append(color("  ↳ resops resolves your group by name (resops-<name>-vg); set "
                       "workload.vm_group_id in config/workshop.yaml only to gate another group", DIM))
    return lines
