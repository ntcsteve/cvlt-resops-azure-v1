# Platform identity + policy, read from the ONE source: config/workshop.yaml.
locals {
  platform = yamldecode(file("${path.module}/../../config/workshop.yaml")).platform
  tiers    = yamldecode(file("${path.module}/../../config/tiers.yaml")).tiers
}

provider "commvault" {
  web_service_url = local.platform.web_service_url
  ignore_cert     = false
  # api_token from CV_TER_TOKEN env var
}

# ── M1 ── the hypervisor is ADOPTED, not created (one-off UI/platform config).
# Its client id is supplied as a variable and passed through to workloads/.
# (We do NOT terraform commvault_azure_hypervisor: this token can't see access nodes,
#  and a 2nd hypervisor on the same subscription risks conflict. Set-once in the UI.)

# ── M2 ── one plan per tier, from config/tiers.yaml. PROVEN: commvault_plan (inline storage by name).
# The tier's RPO sets the plan's backup frequency, and the resops gate enforces the tier's
# rpo_hours/rto_minutes bars on every run. This simple resource expresses RPO in whole DAYS only –
# fine for the workshop, where the tier is a declarative label.
#
# PRODUCTION-REAL RPO: to make tier1 actually back up every 8h (not just declare it), swap this
# for `commvault_plan_server` with an rpo{} block of backupFrequency schedules (sub-day, txn-log,
# synthetic-full). Heavier, still declarative. See the README (Production).
resource "commvault_plan" "tier" {
  for_each                   = local.tiers
  plan_name                  = "resops-${each.key}"
  backup_destination_name    = "Primary"
  backup_destination_storage = local.platform.storage_pool_name # an EXISTING managed pool (set-once, like the hypervisor)
  retention_period_days      = each.value.retention_days
  rpo_in_days                = max(1, floor(each.value.rpo_hours / 24))
}
