"""
The evidence contract — the stable shape a platform team builds on.

A run produces one Bundle: a versioned, machine-readable record of how each
ResOps function judged the environment. CI gates and dashboards depend on this
schema, so it changes deliberately (bump SCHEMA_VERSION) — never casually.
"""
from __future__ import annotations

import enum
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA_VERSION = "3"  # v2: gate section; v3: framework crosswalk in `compliance`

# Each ResOps function spoken in the dialect a cloud-native engineer already
# knows. Surfaced at runtime and in the bundle so the tool teaches as it runs.
DEVOPS_LENS = {
    "discover": "like service discovery — is the workload onboarded?",
    "protect": "like GitOps drift — declared vs actual coverage",
    "detect": "like observability — health checks & alerting",
    "recover": "like rollback readiness — RPO & SLA",
    "validate": "like a chaos drill — prove recovery in isolation",
    "improve": "like a regression gate — trend & audit trail",
    "continuous_business": "Continuous Service — a promotion gate: safe to ship to prod?",
}


class Outcome(enum.Enum):
    """One verdict per function. Four states, never ambiguous."""
    PASS = ("PASS", "32")   # proven, with evidence
    GAP = ("GAP", "33")     # works, but intent isn't met — a finding, not a crash
    FAIL = ("FAIL", "31")   # broken: network, auth, or unexpected response
    SKIP = ("SKIP", "90")   # not run (gated out, or feature disabled)

    @property
    def label(self) -> str:
        return self.value[0]

    @property
    def color_code(self) -> str:
        return self.value[1]


@dataclass(frozen=True)
class FunctionResult:
    """One ResOps function's verdict plus the raw evidence behind it."""
    function: str            # e.g. "discover", "recover"
    outcome: Outcome
    summary: str             # one human line: what was found
    evidence: dict = field(default_factory=dict)  # the numbers behind the verdict

    def to_dict(self) -> dict:
        return {
            "function": self.function,
            "outcome": self.outcome.label,
            "devops_lens": DEVOPS_LENS.get(self.function, ""),
            "summary": self.summary,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class Bundle:
    """The whole run. This is the artifact; everything else just fills it."""
    target: str
    run_at: str                      # caller stamps this (scripts can't read the clock)
    results: list[FunctionResult]
    gate: dict | None = None         # the promotion verdict, set only in gate mode
    controls: dict | None = None     # loaded controls.yaml — tags evidence with controls
    findings: list | None = None     # finding lifecycle (open/remediated/verified)

    def summary_counts(self) -> dict:
        counts = {o.label.lower(): 0 for o in Outcome}
        for result in self.results:
            counts[result.outcome.label.lower()] += 1
        return counts

    def exit_code(self) -> int:
        """CI contract: exit = number of FAILs. GAP is loud but non-fatal."""
        return sum(r.outcome is Outcome.FAIL for r in self.results)

    def to_dict(self) -> dict:
        control_map = (self.controls or {}).get("controls", {}) or {}
        functions = []
        for r in self.results:
            entry = r.to_dict()
            tags = control_map.get(r.function, [])
            if tags:                          # tag evidence with the control(s) it supports
                entry["controls"] = tags
            functions.append(entry)
        out = {
            "schema_version": SCHEMA_VERSION,
            "run_at": self.run_at,
            "target": self.target,
            "summary": self.summary_counts(),
            "functions": functions,
        }
        if self.gate is not None:
            gate = dict(self.gate)            # copy — don't mutate the shared verdict dict
            tags = control_map.get("continuous_business", [])
            if tags:
                gate["controls"] = tags
            out["gate"] = gate
        if self.controls is not None:         # the requirement->control->evidence chain
            compliance = {"disclaimer": self.controls.get("disclaimer", "")}
            if "frameworks" in self.controls:
                compliance["frameworks"] = self.controls["frameworks"]
            if "crosswalk" in self.controls:
                compliance["crosswalk"] = self.controls["crosswalk"]
            out["compliance"] = compliance
        if self.findings is not None:
            out["findings"] = [f.to_dict() for f in self.findings]
        return out

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n")


# --------------------------------------------------------------------------- #
# Audit trail — append-only history of runs (the compliance evidence seed)
# --------------------------------------------------------------------------- #
def load_history(path: Path) -> list:
    """Read the append-only run history (JSON-lines). [] if none yet."""
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


GENESIS_HASH = "0" * 64  # prev_hash of the first chained entry


def _entry_hash(prev_hash: str, core: dict) -> str:
    """sha256 over (prev_hash + the entry's own fields). Canonical = sort_keys.

    The hash binds each record to the one before it, so editing any past entry
    breaks every hash after it — a cheap, dependency-free tamper-evidence seal.
    """
    payload = json.dumps({"prev_hash": prev_hash, **core}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def append_history(path: Path, entry: dict) -> None:
    """Append one run's record, hash-chained to the previous record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    history = load_history(path)
    prev_hash = history[-1].get("entry_hash", GENESIS_HASH) if history else GENESIS_HASH
    sealed = {**entry, "prev_hash": prev_hash}
    sealed["entry_hash"] = _entry_hash(prev_hash, entry)
    with path.open("a") as f:
        f.write(json.dumps(sealed) + "\n")


def verify_history(path: Path) -> tuple[bool, int | None]:
    """Re-walk the chain. Returns (ok, first_broken_index). index None if ok.

    Legacy entries with no entry_hash are treated as the unchained genesis
    prefix; chaining is verified from the first sealed entry onward.
    """
    history = load_history(path)
    prev_hash = GENESIS_HASH
    for i, sealed in enumerate(history):
        if "entry_hash" not in sealed:      # pre-chain legacy record — skip, don't fail
            continue
        core = {k: v for k, v in sealed.items() if k not in ("prev_hash", "entry_hash")}
        if sealed.get("prev_hash") != prev_hash:
            return False, i
        if _entry_hash(prev_hash, core) != sealed["entry_hash"]:
            return False, i
        prev_hash = sealed["entry_hash"]
    return True, None


def history_entry(run_at: str, target: str, results: list,
                  state: str | None = None) -> dict:
    """Compact, append-only record of one run: outcomes, key metrics, and (since
    the readiness ladder) the run's State — the seed the Improve trend compares
    against next run. `state` is optional so legacy callers keep working; entries
    without it are simply not comparable as a trend (treated as baseline)."""
    metrics = {}
    for result in results:
        for key in ("rpo_hours", "sla_status"):
            if key in result.evidence:
                metrics[key] = result.evidence[key]
    entry = {
        "run_at": run_at,
        "target": target,
        "outcomes": {r.function: r.outcome.label for r in results},
        "metrics": metrics,
    }
    if state is not None:
        entry["state"] = state
    return entry
