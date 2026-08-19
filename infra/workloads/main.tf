# config/workshop.yaml is the ONE source – Terraform provisions from `workload` +
# `platform`; the operator lane and the gate read the same file. Nothing hardcoded.
locals {
  workshop = yamldecode(file("${path.module}/../../config/workshop.yaml"))
  platform = local.workshop.platform
  workload = local.workshop.workload
  tiers    = yamldecode(file("${path.module}/../../config/tiers.yaml")).tiers
}

provider "azurerm" {
  features {}
  subscription_id = local.platform.subscription_id
}

# Fail the plan early (with the fix) if the declared tier isn't in config/tiers.yaml.
resource "terraform_data" "tier_check" {
  lifecycle {
    precondition {
      condition     = contains(keys(local.tiers), local.workload.tier)
      error_message = "workload.tier '${local.workload.tier}' is not defined in config/tiers.yaml (e.g. tier1, tier2)."
    }
  }
}

# One workload, declared in config/workshop.yaml's `workload` block. Protect/backup/
# restore are the operator lane's job (token-native) – this root only provisions +
# grants IAM and publishes the `workload` contract (outputs.tf). vm_size/location are
# optional in the yaml; the eastus2 workshop defaults live here (the module has none).
module "vm" {
  source                 = "../modules/azure-vm"
  name                   = local.workload.name
  location               = try(local.workload.location, "eastus2")
  vm_size                = try(local.workload.vm_size, "Standard_F1als_v7")
  commvault_sp_object_id = local.platform.commvault_sp_object_id
  tags = {
    managed_by = "resops-cvlt-azure"
    resops_run = local.workload.name                   # greppable handle across Azure + Commvault
    tier       = local.workload.tier
    env        = try(local.workload.env, "unspecified")
    owner      = try(local.workload.owner, "unspecified")
  }
}
