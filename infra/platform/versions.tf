terraform {
  required_version = ">= 1.5"
  required_providers {
    commvault = {
      source  = "Commvault/commvault"
      version = "~> 1.2"
    }
  }
}
