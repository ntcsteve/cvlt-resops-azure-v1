# Everything you need to use the stack, and the one command that feeds it.
output "grafana_url" {
  value = "http://${azurerm_public_ip.this.ip_address}:3000"
}

output "grafana_user" {
  value = "admin"
}

output "grafana_password" {
  value     = random_password.grafana.result
  sensitive = true # read it with: terraform output -raw grafana_password
}

output "pushgateway_url" {
  value = "http://${azurerm_public_ip.this.ip_address}:9091"
}

# The whole integration, in one line. No agent, no scrape config, no service
# discovery — the metrics come from evidence a run already wrote.
output "publish_command" {
  value = join(" ", [
    "python3 -m resops metrics config/estate.yaml |",
    "curl --data-binary @- http://${azurerm_public_ip.this.ip_address}:9091/metrics/job/resops",
  ])
}
