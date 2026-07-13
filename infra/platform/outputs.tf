# After `terraform apply` here, copy plan_ids into config/workshop.yaml:
#
#   terraform -chdir=infra/platform output plan_ids
#   → {"tier1": 42, "tier2": 99}
#
# Set platform.plan_id to the id for your workload's tier, then proceed to
# `terraform -chdir=infra/workloads apply`.

output "plan_ids" {
  description = "tier -> plan id. Copy the relevant id to platform.plan_id in config/workshop.yaml."
  value       = { for k, p in commvault_plan.tier : k => p.id }
}

output "hypervisor_client_id" {
  description = "The adopted hypervisor client id (passthrough), for workloads' vm_group."
  value       = local.platform.hypervisor.id
}
