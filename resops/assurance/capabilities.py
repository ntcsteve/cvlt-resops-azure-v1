"""
Resilience capabilities – the STABLE SPINE of the crosswalk.

Each ResOps check evidences one or more abstract *capabilities*. Frameworks
(DORA, NIST, APRA, …) don't map to our checks directly – they map their control
references onto these capabilities. That indirection is what makes regimes
interchangeable: we own the check→capability mapping once, and a framework pack
only has to answer "what's your reference for this capability?".

These IDs are a contract. They live in code (not config) because they're ours
and change rarely – only when the checks themselves change. Add a framework by
dropping a YAML pack in config/frameworks/; you never touch this file for that.
"""
from __future__ import annotations

# function -> the capabilities its evidence supports. Keep ids stable.
CAPABILITIES = {
    "discover": [
        {"id": "CAP-ASSET-IDENTIFICATION",
         "evidences": "the workload is identified and onboarded for protection"},
    ],
    "protect": [
        {"id": "CAP-BACKUP-COVERAGE",
         "evidences": "the workload is actually covered by a backup policy"},
    ],
    "detect": [
        {"id": "CAP-BACKUP-MONITORING",
         "evidences": "backup health is monitored; failures are visible"},
    ],
    "recover": [
        {"id": "CAP-RECOVERY-READINESS",
         "evidences": "recoverable now – RPO within tolerance, restore enabled"},
    ],
    "scan": [
        # Wording matters here more than anywhere else in this file. It used to read
        # "no threat is recorded against the point we would restore from", which is
        # the absence-of-evidence claim the Scan rung was rebuilt to reject: a scan
        # that never ran also records no threat. The rung now demands a NAMED
        # attester that actually opened the recovery point, so the control text has
        # to claim that and nothing more.
        {"id": "CAP-RECOVERY-POINT-TRUST",
         "evidences": "a named attester opened the point we would restore from "
                      "and verified its contents"},
    ],
    "validate": [
        {"id": "CAP-RESTORE-TESTED",
         "evidences": "recovery has been proven by a real restore, not assumed"},
    ],
    "improve": [
        {"id": "CAP-EVIDENCE-TRAIL",
         "evidences": "recoverability tested over time; regressions surfaced"},
    ],
    "continuous_business": [
        {"id": "CAP-GOVERNED-CHANGE",
         "evidences": "promotion gated on proven recovery; risk-acceptance logged"},
    ],
}
