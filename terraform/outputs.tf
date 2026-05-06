# Service Account
output "service_account_email" {
  description = "Service account email for Digital Twin operations"
  value       = google_service_account.digitaltwin_sa.email
}

# Webhook Proxy
output "webhook_proxy_url" {
  description = "Cloud Function URL for Slack webhook proxy"
  value       = module.webhook.function_url
}

# VM Template
output "vm_template_name" {
  description = "Compute Engine instance template name"
  value       = module.vm.instance_template_name
}

# Database
output "postgres_disk_name" {
  description = "Persistent disk name for PostgreSQL data"
  value       = module.database.postgres_disk_name
}

# Pub/Sub Topics
output "slack_webhooks_topic" {
  description = "Pub/Sub topic for Slack webhooks"
  value       = google_pubsub_topic.slack_webhooks.name
}

output "vm_lifecycle_topic" {
  description = "Pub/Sub topic for VM lifecycle events"
  value       = google_pubsub_topic.vm_lifecycle.name
}

# Networking
output "network_name" {
  description = "VPC network name"
  value       = module.networking.network_name
}

output "subnet_name" {
  description = "Subnet name"
  value       = module.networking.subnet_name
}

# Storage
output "function_source_bucket" {
  description = "Cloud Storage bucket for function source code"
  value       = google_storage_bucket.function_source.name
}

# Instructions
output "setup_instructions" {
  description = "Manual setup steps required"
  value       = <<EOT
Manual Setup Required:

1. Update Slack App webhook URL:
   https://api.slack.com/apps → Your App → Event Subscriptions
   Set Request URL to: ${module.webhook.function_url}

2. Create .tfvars file with your values:
   cp terraform.tfvars.example terraform.tfvars
   Edit terraform.tfvars with your project_id and slack_signing_secret

3. Deploy with:
   terraform init
   terraform plan -var-file=terraform.tfvars
   terraform apply -var-file=terraform.tfvars

4. After deployment, update your .env file:
   DATABASE_URL=postgresql://user:pass@VM_EXTERNAL_IP/digitaltwin
   (Get VM IP from GCP Console after first startup)
EOT
}
