"""
The ResOps runner — three modes over the same read-only readiness ladder:

  python -m resops [config.yaml]          climb the ladder; exit = number of read FAILs
  python -m resops gate [config.yaml]     the promotion gate; exit 0 PROMOTE / 1 HOLD
  python -m resops verify [config.yaml]   audit the hash-chained trail; exit 0 intact

Each workload is placed on ONE rung of the readiness ladder —
UNDISCOVERED → DISCOVERED → PROTECTED → MONITORED → RECOVERABLE → VALIDATED —
by classify() (resops/state.py). The runner gathers the reads, prints the rung,
the stage it's blocked on, and the trend since last run, then writes the evidence
bundle + audit trail. `gate` is Continuous Service: promote only if the workload
reached VALIDATED and the proof is fresh. Add --allow-stale to ship on aged-but-
clean proof (logged as acknowledged risk). Add --detail for the per-stage rows.
Nothing here mutates your environment.

Config declares one `workload:` or a `workloads:` list (a resilience programme
across critical functions). Each workload keeps its own evidence subdir + hash
chain; a top-level summary.json rolls them up. The gate HOLDs if ANY workload
isn't VALIDATED — criticality is recorded as evidence, never a way to ship past it.
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import json
import sys
from pathlib import Path

import yaml

from .assurance.controls import load_controls
from .assurance.findings import track_findings
from .assurance.junit import write_junit
from .assurance.report import write_report
from .client import AuthError, Client, load_credentials
from .config import load_tiers, platform_url
from .evidence import (
    DEVOPS_LENS, Bundle, append_history, history_entry, load_history, verify_history,
)
from .gate import gate
from .reads import _age_days, _rpo_hours, _rto_minutes, list_vmgroups
from .render import (
    DIM, GREEN, RED, YELLOW, color, ladder_to_results, render_detail, render_headline,
    render_vmgroups,
)
from .state import Reads, classify, gather, trend

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config" / "workshop.yaml"
ENV_PATH = ROOT / ".env"


def reads_from_fixture(rel_path: str) -> Reads:
    """Build Reads from a committed JSON fixture — the no-cloud demo path. This is
    the same Reads that gather() folds live API GETs into, so the demo drives the
    real ladder, gate, and crosswalk with zero network, token, or tenant. Unknown
    keys (e.g. a leading `_comment`) are ignored so fixtures can self-document."""
    data = json.loads((ROOT / rel_path).read_text())
    fields = {f.name for f in dataclasses.fields(Reads)}
    return Reads(**{k: v for k, v in data.items() if k in fields})

CONFIG_ERROR = 2  # exit code for bad config/auth, distinct from read FAILs / HOLD

# Subcommands that take over from the default ladder climb.
SUBCOMMANDS = ("gate", "verify", "list")

USAGE = """resops — read-only resilience readiness ladder + promotion gate

Usage:
  python -m resops [config] [--detail]         climb the ladder (exit = number of read FAILs)
  python -m resops gate [config] [--allow-stale] [--detail]
                                               promotion gate (exit 0 PROMOTE / 1 HOLD)
  python -m resops list [config]               list VM groups + ids (confirm your workload's group)
  python -m resops verify [config]             audit the hash-chained trail (exit 0 intact)
  python -m resops help                        show this message

config defaults to config/workshop.yaml. Nothing here mutates your environment."""


def die(message: str) -> int:
    print(color(message, RED))
    return CONFIG_ERROR


def _display(path: Path) -> str:
    """Path relative to the repo root for tidy output — or absolute if it lives
    outside the repo (e.g. a CI artifacts dir, where relative_to would crash)."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _looks_like_command(arg: str) -> bool:
    """A bare first word that isn't a config file — likely a mistyped subcommand."""
    return not arg.endswith((".yaml", ".yml")) and not Path(arg).exists()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    # Tiny hand-parse: help, then `gate`/`verify` subcommand + flags + optional config.
    if argv and argv[0] in ("help", "--help", "-h"):
        print(USAGE)
        return 0

    subcommand = argv[0] if argv and argv[0] in SUBCOMMANDS else None
    if subcommand:
        argv = argv[1:]
    elif argv and not argv[0].startswith("-") and _looks_like_command(argv[0]):
        print(USAGE)
        return die(f"\nUnknown command: {argv[0]}")
    gate_mode = subcommand == "gate"
    allow_stale = "--allow-stale" in argv
    detail = "--detail" in argv
    positional = [a for a in argv if not a.startswith("-")]
    config_path = Path(positional[0]) if positional else DEFAULT_CONFIG

    if not config_path.exists():
        return die(f"Missing config: {config_path}")
    config = yaml.safe_load(config_path.read_text()) or {}

    base_dir = ROOT / config.get("evidence_dir", "evidence")
    workloads, flat = _workloads(config)

    # Validate declared tiers early — fail with the fix before any API call.
    known_tiers = load_tiers()
    for w in workloads:
        t = w.get("tier")
        if t and t not in known_tiers:
            return die(f"workload '{w['name']}': tier '{t}' not in config/tiers.yaml"
                       f" — defined: {', '.join(known_tiers) or 'none'}")

    # `verify` audits the hash-chained trail(s) — no tenant needed.
    if subcommand == "verify":
        return _verify(base_dir, workloads)

    # Offline demo: when every workload reads from a committed `fixture:`, no
    # tenant, token, or network is needed — the no-cloud "see it first" path. The
    # same classify → gate → crosswalk runs; only the reads are canned.
    offline = bool(workloads) and all(w.get("fixture") for w in workloads)

    if offline:
        target, client = "offline fixture — no cloud", None
    else:
        # The API URL has ONE live home: workshop.yaml's platform.web_service_url —
        # the single source both the read (resops) and write (op) lanes read, so
        # they can't drift onto different tenants.
        target = str(config.get("target") or platform_url() or "").rstrip("/")
        if not target.startswith(("http://", "https://")):
            return die(f"no API URL — set platform.web_service_url in config/workshop.yaml; got '{target}'")
        creds = load_credentials(ENV_PATH)
        if not creds.access_token:
            return die("CV_ACCESS_TOKEN not set — copy .env.example to .env")
        client = Client(target, creds, ENV_PATH)

    # `list` is the onboarding lookup — needs a live tenant.
    if subcommand == "list":
        if offline:
            return die("`list` needs a live tenant — this config is an offline fixture")
        return _list(client)

    if not workloads:
        return die("config must define a `workload:` or a `workloads:` list")

    try:
        controls = load_controls(config)   # crosswalk for the configured framework(s)
    except FileNotFoundError as err:
        return die(str(err))

    print(f"Target: {target}\n")
    run_at = _dt.datetime.now(_dt.timezone.utc).isoformat()

    summaries = []
    try:
        for w in workloads:
            w_dir = base_dir / _slug(w["name"])
            summaries.append(_run_one(client, config, w, controls, w_dir, run_at,
                                      target, gate_mode, allow_stale, detail, multi=not flat))
    except AuthError as err:
        return die(f"Auth failed: {err}")

    return _aggregate(summaries, base_dir, run_at, target, gate_mode, flat)


# --------------------------------------------------------------------------- #
# Workload resolution — a single `workload:` or a `workloads:` programme.
# --------------------------------------------------------------------------- #
def _resolve_policy(workload: dict, config: dict) -> dict:
    """Assemble the promotion gate policy.

    Priority (high → low):
      1. workload.promote_policy  — per-workload explicit override
      2. config.gate / config.promote_policy  — programme-level default
      3. tier bars from tiers.yaml  — auto-injected for any key NOT already declared

    Tier bars fill gaps; they never overwrite explicit declarations. Unknown tier
    names warn and continue — no tiers.yaml means no RPO/RTO bars (still enforces
    freshness and VALIDATED state).
    """
    base = dict(workload.get("promote_policy")
                or config.get("gate")
                or config.get("promote_policy")
                or {})
    tier_name = workload.get("tier")
    if tier_name:
        tier = load_tiers().get(tier_name)
        if not tier:
            # Defensive guard for direct callers (e.g. tests). main() validates
            # tiers early and die()s before reaching here, so this path is only
            # reachable when _resolve_policy is called outside the main flow.
            print(color(f"  warning: tier '{tier_name}' not found in tiers.yaml"
                        " — no RPO/RTO bars applied", YELLOW))
        else:
            if "rpo_target_hours" not in base and "rpo_hours" in tier:
                base["rpo_target_hours"] = tier["rpo_hours"]
            if "rto_target_minutes" not in base and "rto_minutes" in tier:
                base["rto_target_minutes"] = tier["rto_minutes"]
    return base


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-") or "workload"


def _normalize(w: dict) -> dict:
    # `name` is the codename declared in workshop.yaml; `vm_name` is what the reads
    # key off (the VM inside the group). For an op-created workload they're equal,
    # so accept either and fill the other.
    name = w.get("name") or w.get("vm_name") or "workload"
    return {**w, "name": name, "vm_name": w.get("vm_name") or name,
            "criticality": w.get("criticality", "unspecified"),
            "env": w.get("env", "unspecified"),
            "owner": w.get("owner", "unspecified")}


def _workloads(config: dict) -> tuple[list, bool]:
    """Return (workloads, flat). flat=True keeps the singular-config flat layout."""
    if config.get("workloads"):
        return [_normalize(w) for w in config["workloads"]], False
    single = config.get("workload")
    return ([_normalize(single)] if single else []), True


def _verify(base_dir: Path, workloads: list) -> int:
    paths = [base_dir / _slug(w["name"]) / "history.jsonl" for w in workloads]
    broken = []
    for p in paths:
        ok, where = verify_history(p)
        if not ok:
            broken.append((p, where))
    if not broken:
        print(color("  audit trail intact — hash chain verified", GREEN))
        return 0
    for path, where in broken:
        print(color(f"  TAMPERED — {_display(path)} breaks at entry {where}", RED))
    return 1


def _list(client) -> int:
    """The onboarding lookup — print every VM group + id to confirm a workload's group
    exists (resops resolves it by name; the id is only for the optional override).
    Read-only; needs target + token but no workload."""
    try:
        vmgroups, err = list_vmgroups(client)
    except AuthError as auth_err:
        return die(f"Auth failed: {auth_err}")
    if err:
        return die(f"could not list VM groups: {err}")
    for line in render_vmgroups(vmgroups):
        print(line)
    return 0


# --------------------------------------------------------------------------- #
# Climb one workload's ladder (and judge the gate, in gate mode).
# --------------------------------------------------------------------------- #
def _open_count(findings) -> str:
    n = sum(f.status == "OPEN" for f in findings)
    return f" · {n} open finding{'s' if n != 1 else ''}" if n else ""


def _run_one(client, config, workload, controls, w_dir, run_at, target,
             gate_mode, allow_stale, detail, multi) -> dict:
    history = load_history(w_dir / "history.jsonl")

    # Read once, classify to a state, compare to history — the whole ladder.
    # A canned `fixture:` (the offline demo) stands in for the live API reads.
    reads = (reads_from_fixture(workload["fixture"]) if workload.get("fixture")
             else gather(client, workload))
    ladder = classify(reads)
    tr = trend(ladder.state, history)

    # Numbers the clock-free classify() can't hold, measured here at the edge.
    metrics = {"rpo_hours": _rpo_hours(reads.vm),
               "proof_age_days": _age_days(reads.proof) if reads.proof else None,
               "rto_minutes": _rto_minutes(reads.proof) if reads.proof else None}

    results = ladder_to_results(ladder, tr, metrics)
    stage_results = results[:-1]   # the 5 stages (improve is cross-cutting, not a finding)
    findings = track_findings(workload["name"], run_at, stage_results, history)

    verdict = None
    if gate_mode:
        policy = _resolve_policy(workload, config)
        verdict = gate(ladder, policy, allow_stale=allow_stale, run_at=run_at,
                       proof_age_days=metrics["proof_age_days"], rpo_hours=metrics["rpo_hours"],
                       rto_minutes=metrics["rto_minutes"], regressed=tr.regressed)

    bundle = Bundle(target=target, run_at=run_at, results=results,
                    gate=verdict.to_dict() if verdict else None,
                    controls=controls, findings=findings)
    paths = (w_dir / "bundle.json", w_dir / "history.jsonl", w_dir / "report.md")

    for line in render_headline(workload["name"], workload["criticality"], ladder, tr,
                                multi, rpo_hours=metrics["rpo_hours"],
                                env=workload.get("env", ""),
                                owner=workload.get("owner", "")):
        print(line)
    if detail:
        for line in render_detail(results):
            print(line)
    _finalize(bundle, stage_results, run_at, target, ladder.state.name, paths)
    write_junit(bundle.to_dict(), workload["name"], paths[0].parent / "junit.xml")

    if gate_mode:
        _print_verdict(verdict, paths[0])
    elif not multi:
        print(f"  Evidence: {_display(paths[0])} · Report: {_display(paths[2])}"
              f"{_open_count(findings)}")
    if multi:
        print()
    return {
        "name": workload["name"], "criticality": workload["criticality"],
        "env": workload["env"], "owner": workload["owner"],
        "state": ladder.state.name, "evidence": _display(paths[0]),
        "counts": bundle.summary_counts(),
        "open_findings": sum(f.status == "OPEN" for f in findings),
        "gate": verdict.decision if verdict else None,
        "exit": verdict.exit_code if verdict else bundle.exit_code(),
    }


def _finalize(bundle, stage_results, run_at, target, state, paths) -> None:
    """Write the bundle, append the hash-chained history (with state), render the report."""
    bundle_path, history_path, report_path = paths
    bundle_dict = bundle.to_dict()
    bundle.write(bundle_path)
    append_history(history_path, history_entry(run_at, target, stage_results, state))
    write_report(bundle_dict, report_path)


def _print_verdict(verdict, bundle_path) -> None:
    print("  " + "─" * 41)
    code = {"PROMOTE": GREEN, "OVERRIDE": YELLOW, "HOLD": RED}[verdict.decision]
    headline = verdict.reasons[0] if verdict.reasons else "recoverability proven"
    print(f"  {color(verdict.decision, code)}  {headline} · exit {verdict.exit_code}")
    print(color(f"  ↳ {DEVOPS_LENS['continuous_business']}", DIM))
    for extra in verdict.reasons[1:]:
        print(color(f"  ↳ {extra}", DIM))
    if verdict.acknowledged_risk:
        print(color(f"  ↳ {_display(bundle_path)}: acknowledged_risk logged", DIM))


# --------------------------------------------------------------------------- #
# Roll the workloads up into one programme verdict + summary.json.
# --------------------------------------------------------------------------- #
def _aggregate(summaries, base_dir, run_at, target, gate_mode, flat) -> int:
    totals = {k: sum(s["counts"][k] for s in summaries) for k in ("pass", "gap", "fail", "skip")}
    opens = sum(s["open_findings"] for s in summaries)
    holds = [s["name"] for s in summaries if s["gate"] == "HOLD"]
    overridden = [s["name"] for s in summaries if s["gate"] == "OVERRIDE"]
    if gate_mode:
        exit_code, decision = (1, "HOLD") if holds else (0, "PROMOTE")
    else:
        exit_code, decision = sum(s["counts"]["fail"] for s in summaries), None

    summary = {
        "run_at": run_at, "target": target, "mode": "gate" if gate_mode else "loop",
        "workloads": summaries,
        "aggregate": {"decision": decision, "totals": totals, "open_findings": opens,
                      "overridden": overridden, "exit": exit_code},
    }
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    if not flat:   # only roll up when it's a multi-workload programme
        n = len(summaries)
        if gate_mode and decision == "HOLD":
            print(color(f"AGGREGATE  HOLD — {', '.join(holds)} · exit {exit_code}", RED))
        elif gate_mode:
            extra = f" ({len(overridden)} overridden)" if overridden else ""
            print(color(f"AGGREGATE  PROMOTE — {n} workload(s) clear{extra} · exit 0", GREEN))
        else:
            states = ", ".join(f"{s['name']}={s['state']}" for s in summaries)
            print(f"AGGREGATE  {n} workload(s) · {states} · {opens} open · exit {exit_code}")
        print(f"Summary: {_display(base_dir / 'summary.json')}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
