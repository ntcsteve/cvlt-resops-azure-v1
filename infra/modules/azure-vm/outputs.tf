output "vm_name" {
  value = azurerm_linux_virtual_machine.this.name
}

output "vm_id" {
  value = azurerm_linux_virtual_machine.this.id
}

output "resource_group" {
  value = azurerm_resource_group.this.name
}

# The Azure-assigned VM GUID (vmId) == Commvault's strGUID. This IS the protect
# GUID — feed it to content.virtualMachines[].GUID. (Proven: falcon run.)
output "vm_guid" {
  value = azurerm_linux_virtual_machine.this.virtual_machine_id
}

# The restore staging storage account — feed this to the restore payload's
# Datastore so the VALIDATED drill has somewhere to stage the VHD.
output "restore_storage_account" {
  value = azurerm_storage_account.restore.name
}

# ── The contract ───────────────────────────────────────────────────────────
# operator/ reads these so it never reconstructs a name or pins a size. Every
# workload fact the write lane needs comes from here — one source, flows down.
output "location" {
  value = azurerm_resource_group.this.location
}

output "vm_size" {
  value = azurerm_linux_virtual_machine.this.size
}

output "vnet_name" {
  value = azurerm_virtual_network.this.name
}

output "subnet_id" {
  value = azurerm_subnet.this.id
}
