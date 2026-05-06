variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region"
  type        = string
}

variable "zone" {
  description = "GCP Zone"
  type        = string
}

variable "disk_size" {
  description = "Persistent disk size in GB"
  type        = number
  default     = 50
}

# Persistent disk for PostgreSQL data
resource "google_compute_disk" "postgres_data" {
  name = "digitaltwin-postgres-data"
  type = "pd-ssd"
  zone = var.zone
  size = var.disk_size

  # Prevent accidental deletion
  lifecycle {
    prevent_destroy = true
  }

  labels = {
    environment = "production"
    component   = "database"
    app         = "digitaltwin"
  }
}

# Outputs
output "postgres_disk_name" {
  description = "Name of the PostgreSQL data disk"
  value       = google_compute_disk.postgres_data.name
}

output "postgres_disk_self_link" {
  description = "Self-link of the PostgreSQL data disk"
  value       = google_compute_disk.postgres_data.self_link
}

output "postgres_disk_size" {
  description = "Size of the PostgreSQL data disk"
  value       = google_compute_disk.postgres_data.size
}
