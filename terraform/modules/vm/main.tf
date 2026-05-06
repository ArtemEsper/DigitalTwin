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

variable "service_account" {
  description = "Service account email"
  type        = string
}

variable "postgres_disk" {
  description = "PostgreSQL persistent disk name"
  type        = string
}

variable "network" {
  description = "VPC network name"
  type        = string
}

variable "subnetwork" {
  description = "VPC subnetwork name"
  type        = string
}

variable "machine_type" {
  description = "VM machine type"
  type        = string
  default     = "e2-medium"
}

# Instance template for Digital Twin VM
resource "google_compute_instance_template" "digitaltwin" {
  name_prefix  = "digitaltwin-"
  machine_type = var.machine_type
  region       = var.region

  # Use Container-Optimized OS for Docker
  disk {
    source_image = "cos-cloud/cos-stable"
    auto_delete  = true
    boot         = true
  }

  # Attach PostgreSQL data disk — must survive VM deletion
  disk {
    source      = var.postgres_disk
    device_name = "postgres-data"
    mode        = "READ_WRITE"
    boot        = false
    auto_delete = false
  }

  network_interface {
    network    = var.network
    subnetwork = var.subnetwork
    access_config {} # External IP
  }

  service_account {
    email = var.service_account
    scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
      "https://www.googleapis.com/auth/pubsub"
    ]
  }

  metadata = {
    startup-script = file("scripts/startup.sh")
  }

  tags = ["digitaltwin", "http-server", "https-server"]

  lifecycle {
    create_before_destroy = true
  }

  labels = {
    environment = "production"
    app         = "digitaltwin"
  }
}

# Outputs
output "instance_template_name" {
  description = "Compute Engine instance template name"
  value       = google_compute_instance_template.digitaltwin.name
}

output "instance_template_self_link" {
  description = "Instance template self-link"
  value       = google_compute_instance_template.digitaltwin.self_link
}
