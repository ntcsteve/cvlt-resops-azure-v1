"""
Finding lifecycle (Tier 2, item T2-4).

A *finding* is a non-PASS outcome on a ResOps function. DORA's testing program
(Art. 24) wants findings logged, then fixed, then the fix VERIFIED – with progress
retained. We DERIVE that lifecycle from the hash-chained history each run, so it's
evidence we recompute, not mutable state we have to trust ourselves to maintain.

Status is an explicit, irrefutable state machine over the recent outcomes:

  OPEN        currently non-PASS (GAP/FAIL)
  REMEDIATED  PASS now, was non-PASS last run            (just fixed)
  VERIFIED    PASS now and last run, was non-PASS before (fix has held a cycle)
  (stable PASS produces no finding)

A finding's id is stable across runs (scope + function) – scope is the workload
name, so ids are per-workload-stable and don't collide across workloads. The same
issue keeps the same id whether it's open, remediated, or it later reopens.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .report import risk_rating

NONPASS = ("GAP", "FAIL")


def _fid(scope: str, function: str) -> str:
    """Stable finding id – survives summary changes, reopens with the same id."""
    return hashlib.sha256(f"{scope}:{function}".encode()).hexdigest()[:12]


@dataclass(frozen=True)
class Finding:
    id: str
    function: str
    status: str        # OPEN | REMEDIATED | VERIFIED
    risk: str          # meaningful only while OPEN
    runs_open: int     # consecutive runs non-PASS, including this one (OPEN only)
    since: str         # run_at the current open streak began (OPEN only)

    def to_dict(self) -> dict:
        d = {"id": self.id, "function": self.function, "status": self.status}
        if self.status == "OPEN":
            d.update(risk=self.risk, runs_open=self.runs_open, since=self.since)
        return d


def track_findings(scope: str, run_at: str, results: list, history: list) -> list:
    """Derive the finding lifecycle for this run from the audit trail.

    `scope` namespaces finding ids (the workload name) so they're stable per
    workload and never collide across workloads in a multi-workload program.
    """
    findings = []
    for r in results:
        fn = r.function
        cur = r.outcome.label
        prior = [(h.get("run_at", ""), h["outcomes"].get(fn))
                 for h in history if fn in h.get("outcomes", {})]
        prev = prior[-1][1] if prior else None
        prev2 = prior[-2][1] if len(prior) >= 2 else None

        if cur in NONPASS:
            since, runs_open = run_at, 1          # this run, plus any trailing streak
            for ts, outcome in reversed(prior):
                if outcome in NONPASS:
                    runs_open += 1
                    since = ts or since
                else:
                    break
            findings.append(Finding(_fid(scope, fn), fn, "OPEN",
                                    risk_rating(fn, cur), runs_open, since))
        elif prev in NONPASS:
            findings.append(Finding(_fid(scope, fn), fn, "REMEDIATED", "none", 0, ""))
        elif prev == "PASS" and prev2 in NONPASS:
            findings.append(Finding(_fid(scope, fn), fn, "VERIFIED", "none", 0, ""))
    return findings
