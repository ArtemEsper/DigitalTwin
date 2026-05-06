variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region"
  type        = string
}

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

# VPC Network
resource "google_compute_network" "digitaltwin_vpc" {
  name                    = var.network_name
  auto_create_subnetworks = false
}

# Subnet
resource "google_compute_subnetwork" "digitaltwin_subnet" {
  name          = var.subnet_name
  ip_cidr_range = "10.0.0.0/24"
  region        = var.region
  network       = google_compute_network.digitaltwin_vpc.id
}

# Firewall rules
resource "google_compute_firewall" "allow_ssh" {
  name    = "allow-ssh"
  network = google_compute_network.digitaltwin_vpc.name

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["ssh", "digitaltwin"]
}

resource "google_compute_firewall" "allow_http" {
  name    = "allow-http"
  network = google_compute_network.digitaltwin_vpc.name

  allow {
    protocol = "tcp"
    ports    = ["80", "443", "8000"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["http-server", "https-server", "digitaltwin"]
}

resource "google_compute_firewall" "allow_internal" {
  name    = "allow-internal"
  network = google_compute_network.digitaltwin_vpc.name

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "udp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "icmp"
  }

  source_ranges = ["10.0.0.0/24"]
}

# Outputs
output "network_name" {
  value = google_compute_network.digitaltwin_vpc.name
}

output "subnet_name" {
  value = google_compute_subnetwork.digitaltwin_subnet.name
}

output "network_self_link" {
  value = google_compute_network.digitaltwin_vpc.self_link
}
