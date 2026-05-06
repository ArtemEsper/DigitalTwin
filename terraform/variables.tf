variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "GCP Zone"
  type        = string
  default     = "us-central1-a"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "dev"
}

# VM Configuration
variable "vm_machine_type" {
  description = "Compute Engine machine type"
  type        = string
  default     = "e2-medium"
}

variable "postgres_disk_size" {
  description = "PostgreSQL data disk size in GB"
  type        = number
  default     = 50
}

# Network Configuration
variable "network_name" {
  description = "VPC network name"
  type        = string
  default     = "digitaltwin-network"
}

variable "subnet_name" {
  description = "Subnet name"
  type        = string
  default     = "digitaltwin-subnet"
}

# Slack signing secret — used only by the webhook proxy Cloud Function.
# All other secrets (anthropic_api_key, slack_bot_token, etc.) are managed
# directly in GCP Secret Manager and never passed through Terraform.
variable "slack_signing_secret" {
  description = "Slack signing secret for webhook verification (passed to webhook proxy function)"
  type        = string
  sensitive   = true
  default     = ""
}

# Database Configuration
variable "postgres_version" {
  description = "PostgreSQL version"
  type        = string
  default     = "POSTGRES_15"
}

variable "postgres_tier" {
  description = "PostgreSQL machine tier (if using Cloud SQL instead)"
  type        = string
  default     = "db-f1-micro"
}
