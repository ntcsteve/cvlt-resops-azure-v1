terraform {
  required_version = ">= 1.5"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 4.0" }
    random  = { source = "hashicorp/random", version = "~> 3.0" }
    # No commvault provider: protect/backup/restore are the operator lane's job
    # (token-native), because the provider can only write rule-based content the
    # resops ladder can't read. See operator/.
  }
}
