# The observability stack – ONE small VM running pushgateway + prometheus + grafana.
#
# WHY A SEPARATE ROOT: infra/platform/ is Commvault plan-as-code (commvault
# provider, CV_TER_TOKEN). This is Azure infrastructure with a different lifecycle
# – you deploy it before a workshop and destroy it after. Separate root, separate
# state, no shared blast radius.
#
# WHY NOTHING IS INSTALLED ON PROTECTED WORKLOADS: this stack scrapes NOTHING.
# `resops metrics` reads the evidence a run already wrote and pushes it here. No
# agent, no node_exporter, no VNet peering. (Every workload VNet is 10.123.0.0/16,
# so they overlap and could never be peered anyway – a scrape design would have
# hit that wall.)
#
# IT IS CATTLE. No volumes, no persistence. Destroy it and rebuild with one apply;
# the metrics come back the next time anything runs `resops metrics`.
locals {
  platform = yamldecode(file("${path.module}/../../config/workshop.yaml")).platform
  name     = "resops-observability"
}

provider "azurerm" {
  features {}
  subscription_id = local.platform.subscription_id
}

resource "random_password" "grafana" {
  length  = 20
  special = false # keeps it copy-pasteable into a browser prompt at 8am
}

resource "azurerm_resource_group" "this" {
  name     = "${local.name}-rg"
  location = var.location
  tags     = { managed_by = "resops-cvlt-azure", role = "observability" }
}

resource "azurerm_virtual_network" "this" {
  name                = "${local.name}-vnet"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  # Deliberately NOT 10.123.0.0/16 – that's the workload range. No peering is
  # needed (push, not scrape), but overlapping ranges would foreclose the option.
  address_space = ["10.250.0.0/16"]
}

resource "azurerm_subnet" "this" {
  name                 = "${local.name}-subnet"
  resource_group_name  = azurerm_resource_group.this.name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = ["10.250.1.0/24"]
}

resource "azurerm_public_ip" "this" {
  name                = "${local.name}-pip"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  allocation_method   = "Static"
  sku                 = "Standard"
}

# The room has to reach Grafana, and CI has to reach the pushgateway, so both are
# open to the internet. That is a real trade-off, taken knowingly: Grafana has a
# generated password, the pushgateway only accepts metric writes, and the whole
# stack is destroyed after the workshop. Do not leave it running.
resource "azurerm_network_security_group" "this" {
  name                = "${local.name}-nsg"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name

  security_rule {
    name                       = "grafana"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "3000"
    source_address_prefix      = var.allowed_source
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "pushgateway"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "9091"
    source_address_prefix      = var.allowed_source
    destination_address_prefix = "*"
  }
}

resource "azurerm_network_interface" "this" {
  name                = "${local.name}-nic"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  ip_configuration {
    name                          = "ipconfig1"
    subnet_id                     = azurerm_subnet.this.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.this.id
  }
}

resource "azurerm_network_interface_security_group_association" "this" {
  network_interface_id      = azurerm_network_interface.this.id
  network_security_group_id = azurerm_network_security_group.this.id
}

resource "random_password" "admin" {
  length  = 24
  special = true
}

resource "azurerm_linux_virtual_machine" "this" {
  name                = local.name
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  # BS family on purpose: it does not compete with the Falsv7 quota the workload
  # VMs need. NOTE the regional vCPU ceiling is shared – this VM's 2 vCPUs come
  # off the same 10, leaving 8 for participants (2 each at restore peak).
  size                            = var.vm_size
  admin_username                  = var.admin_username
  admin_password                  = random_password.admin.result
  disable_password_authentication = false
  network_interface_ids           = [azurerm_network_interface.this.id]
  tags                            = { managed_by = "resops-cvlt-azure", role = "observability" }

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

  # Every artifact is a REAL FILE in ./stack/, embedded here rather than restated.
  # That is what lets test-stack.sh run the same compose file locally and prove
  # something about what actually deploys – a test against a copy proves nothing.
  # (file() does not interpolate, so compose's own $${GRAFANA_PASSWORD} survives.)
  custom_data = base64encode(templatefile("${path.module}/cloud-init.yaml", {
    grafana_password = random_password.grafana.result
    compose_yml      = indent(6, file("${path.module}/stack/docker-compose.yml"))
    prometheus_yml   = indent(6, file("${path.module}/stack/prometheus.yml"))
    datasource_yml   = indent(6, file("${path.module}/stack/grafana-datasource.yml"))
    dashboards_yml   = indent(6, file("${path.module}/stack/grafana-dashboards.yml"))
    dashboard_json   = indent(6, file("${path.module}/stack/dashboards/resops.json"))
  }))
}
