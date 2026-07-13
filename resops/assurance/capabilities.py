"""
Resilience capabilities — the STABLE SPINE of the crosswalk.

Each ResOps check evidences one or more abstract *capabilities*. Frameworks
(DORA, NIST, APRA, …) don't map to our checks directly — they map their control
references onto these capabilities. That indirection is what makes regimes
interchangeable: we own the check→capability mapping once, and a framework pack
only has to answer "what's your reference for this capability?".

These IDs are a contract. They live in code (not config) because they're ours
and change rarely — only when the checks themselves change. Add a framework by
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
         "evidences": "recoverable now — RPO within tolerance, restore enabled"},
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
