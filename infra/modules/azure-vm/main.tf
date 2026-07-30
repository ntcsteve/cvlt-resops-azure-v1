terraform {
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 4.0" }
    random  = { source = "hashicorp/random", version = "~> 3.0" }
  }
}

# A minimal Azure Linux VM, discoverable by the Commvault hypervisor (API-level —
# no public IP / NSG needed; discovery enumerates the subscription, not the network).
resource "random_password" "admin" {
  length  = 24
  special = true
}

resource "azurerm_resource_group" "this" {
  name     = "resops-${var.name}-rg"
  location = var.location
  tags     = var.tags
}

# ── Commvault IAM ────────────────────────────────────────────────────────────
# Backup and restore need DIFFERENT Azure permissions. Grant BOTH, or a workload
# that backs up fine will silently fail the restore drill — the gap that cost us
# four failed restores. Each role is scoped as tightly as its job allows.

# (1) CONTROL PLANE — backup snapshots the VM's disk; restore creates the new VM
#     and disk. Contributor on THIS RG covers both. Without it backup fails with
#     "Unable to create a virtual machine snapshot".
resource "azurerm_role_assignment" "commvault" {
  count                = var.commvault_sp_object_id == "" ? 0 : 1
  scope                = azurerm_resource_group.this.id
  role_definition_name = "Contributor"
  principal_id         = var.commvault_sp_object_id
}

# Restore stages the recovered VHD as a BLOB into this storage account, then
# converts it to a managed disk. No staging account = restore fails at the VM-
# create step with "No OS disk found ... datastore []". One per workload, torn
# down with the RG — self-contained, no shared platform state.
resource "random_string" "sa" {
  length  = 8
  lower   = true
  upper   = false
  special = false
  numeric = true
}

locals {
  # Storage-account names are 3–24 chars, lowercase letters+digits only, and
  # globally unique. Sanitise the workload name, cap it, append a random tail.
  sa_name = substr("${replace(lower(var.name), "/[^a-z0-9]/", "")}rst${random_string.sa.result}", 0, 24)
}

resource "azurerm_storage_account" "restore" {
  name                     = local.sa_name
  resource_group_name      = azurerm_resource_group.this.name
  location                 = azurerm_resource_group.this.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  tags                     = var.tags
}

# (2) DATA PLANE — restore WRITES the VHD blob using the SP's Azure AD identity.
#     Contributor cannot do this; without this role the restore fails with
#     "AuthorizationPermissionMismatch ... Unable to write data to the disk".
#     Scoped to the staging account only — least privilege.
resource "azurerm_role_assignment" "commvault_blob" {
  count                = var.commvault_sp_object_id == "" ? 0 : 1
  scope                = azurerm_storage_account.restore.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = var.commvault_sp_object_id
}

resource "azurerm_virtual_network" "this" {
  name                = "resops-${var.name}-vnet"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  address_space       = ["10.123.0.0/16"]
  tags                = var.tags
}

resource "azurerm_subnet" "this" {
  name                 = "resops-${var.name}-subnet"
  resource_group_name  = azurerm_resource_group.this.name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = ["10.123.1.0/24"]
}

resource "azurerm_network_interface" "this" {
  name                = "resops-${var.name}-nic"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  tags                = var.tags
  ip_configuration {
    name                          = "ipconfig1"
    subnet_id                     = azurerm_subnet.this.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_linux_virtual_machine" "this" {
  name                            = var.name
  resource_group_name             = azurerm_resource_group.this.name
  location                        = azurerm_resource_group.this.location
  size                            = var.vm_size
  admin_username                  = var.admin_username
  admin_password                  = random_password.admin.result
  disable_password_authentication = false
  network_interface_ids           = [azurerm_network_interface.this.id]
  tags                            = var.tags

  # NB: os_disk.name is intentionally left unset (Azure auto-names it). Setting it
  # forces VM REPLACEMENT on any existing workload — a module update must never nuke
  # a running VM. The restore drill controls its own (unique) target disk name, so a
  # predictable source name buys nothing. Boring + non-destructive wins.
  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  # Lay down a small service so the workload has code, state, config and a secret —
  # the four things the trust-map exercise asks participants to classify, and the
  # files `op incident` later targets. A bare OS gives a threat scan nothing to find.
  #
  # NB: like os_disk.name, changing custom_data forces VM REPLACEMENT. That's correct
  # for a fresh climb and must never be applied to a workload mid-drill.
  custom_data = base64encode(templatefile("${path.module}/cloud-init.yaml", {
    workload_name = var.name
  }))
}
