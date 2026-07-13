variable "name" { type = string }
variable "location" { type = string }
variable "vm_size" { type = string }
variable "admin_username" {
  type    = string
  default = "azureuser"
}
variable "tags" {
  type    = map(string)
  default = {}
}

# Object id of Commvault's Azure service principal. Granted Contributor on this VM's RG
# so Commvault can snapshot the VM for backup. Empty = skip (e.g. granted elsewhere).
variable "commvault_sp_object_id" {
  type    = string
  default = ""
}
