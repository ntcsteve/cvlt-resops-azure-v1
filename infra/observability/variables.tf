variable "location" {
  type    = string
  default = "eastus2"
}

# BS family – a different quota pool from the workloads' Falsv7, so the stack can
# never starve a participant of a VM. 2 vCPU / 4 GB is ample for three containers
# serving a handful of series.
variable "vm_size" {
  type    = string
  default = "Standard_B2s"
}

variable "admin_username" {
  type    = string
  default = "azureuser"
}

# Lock the stack to your own IP for a private run: -var allowed_source=203.0.113.7
# Default is open because a workshop room arrives from addresses you don't know in
# advance. The stack is destroyed the same day; do not treat it as long-lived.
variable "allowed_source" {
  type    = string
  default = "*"
}
