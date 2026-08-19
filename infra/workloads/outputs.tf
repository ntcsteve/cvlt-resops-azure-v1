# The contract – every fact the operator/ write lane + restore drill need, in one
# output. `op` reads `terraform -chdir=workloads output -json workload` and assumes
# nothing: no reconstructed names, no hardcoded sizes.
output "workload" {
  value = {
    vm_name                 = module.vm.vm_name
    vm_guid                 = module.vm.vm_guid
    resource_group          = module.vm.resource_group
    location                = module.vm.location
    vm_size                 = module.vm.vm_size
    vnet_name               = module.vm.vnet_name
    subnet_id               = module.vm.subnet_id
    restore_storage_account = module.vm.restore_storage_account
  }
}
