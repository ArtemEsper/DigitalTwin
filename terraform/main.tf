terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 4.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

# Enable required APIs
resource "google_project_service" "required_apis" {
  for_each = toset([
    "cloudfunctions.googleapis.com",
    "compute.googleapis.com",
    "sqladmin.googleapis.com",
    "pubsub.googleapis.com",
    "cloudscheduler.googleapis.com",
    "run.googleapis.com",
    "storage.googleapis.com",
    "iam.googleapis.com",
    "monitoring.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "speech.googleapis.com"
  ])

  service = each.key

  disable_on_destroy = false
}

# Service Account for Digital Twin operations
resource "google_service_account" "digitaltwin_sa" {
  account_id   = "digitaltwin-service"
  display_name = "Digital Twin Service Account"
  description  = "Service account for Digital Twin GCP operations"
}

# IAM roles for the service account
resource "google_project_iam_member" "digitaltwin_sa_roles" {
  for_each = toset([
    "roles/compute.admin",                  # Start/stop VMs
    "roles/pubsub.publisher",               # Publish to Pub/Sub
    "roles/pubsub.subscriber",              # Subscribe to Pub/Sub
    "roles/storage.objectAdmin",            # Access Cloud Storage
    "roles/cloudfunctions.invoker",         # Invoke Cloud Functions
    "roles/artifactregistry.reader",        # Read artifact registry (for Cloud Functions deployment)
    "roles/cloudfunctions.serviceAgent",    # Run as Cloud Function
    "roles/monitoring.viewer",              # Read monitoring data
    "roles/logging.logWriter",              # Write logs
    "roles/secretmanager.secretAccessor"    # Access secrets
  ])

  project = var.project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.digitaltwin_sa.email}"
}

# Storage bucket for Cloud Function source code
resource "google_storage_bucket" "function_source" {
  name          = "${var.project_id}-digitaltwin-functions"
  location      = var.region
  force_destroy = true

  uniform_bucket_level_access = true
}

# Storage bucket for voice message audio files
resource "google_storage_bucket" "audio_storage" {
  name          = "${var.project_id}-dt-audio"
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true

  lifecycle_rule {
    action { type = "Delete" }
    condition { age = 90 }   # auto-delete raw audio after 90 days
  }

  depends_on = [google_project_service.required_apis]
}

# Secret Manager resources
resource "google_secret_manager_secret" "anthropic_api_key" {
  secret_id = "anthropic-api-key"
  replication {
    automatic = true
  }
  depends_on = [google_project_service.required_apis]
}

resource "google_secret_manager_secret" "admin_api_key" {
  secret_id = "admin-api-key"
  replication {
    automatic = true
  }
  depends_on = [google_project_service.required_apis]
}

resource "google_secret_manager_secret" "voyage_api_key" {
  secret_id = "voyage-api-key"
  replication {
    automatic = true
  }
  depends_on = [google_project_service.required_apis]
}

resource "google_secret_manager_secret" "subject_id" {
  secret_id = "subject-id"
  replication {
    automatic = true
  }
  depends_on = [google_project_service.required_apis]
}

# Slack secrets
resource "google_secret_manager_secret" "slack_bot_token" {
  secret_id = "slack-bot-token"
  replication {
    automatic = true
  }
  depends_on = [google_project_service.required_apis]
}

resource "google_secret_manager_secret" "slack_signing_secret" {
  secret_id = "slack-signing-secret"
  replication {
    automatic = true
  }
  depends_on = [google_project_service.required_apis]
}

# Secret versions are managed manually via GCP Console or gcloud — NOT by Terraform.
# To set a secret value:
#   echo -n "VALUE" | gcloud secrets versions add SECRET_NAME --data-file=- --project=digitaltwin-gcp-pr

# Modules
module "networking" {
  source = "./modules/networking"

  project_id = var.project_id
  region     = var.region
}

module "database" {
  source = "./modules/database"

  project_id = var.project_id
  region     = var.region
  zone       = var.zone
}

module "webhook" {
  source = "./modules/webhook"

  project_id           = var.project_id
  region               = var.region
  service_account      = google_service_account.digitaltwin_sa.email
  source_bucket        = google_storage_bucket.function_source.name
  slack_signing_secret = var.slack_signing_secret

  depends_on = [google_project_service.required_apis]
}

module "vm" {
  source = "./modules/vm"

  project_id      = var.project_id
  region          = var.region
  zone            = var.zone
  service_account = google_service_account.digitaltwin_sa.email
  postgres_disk   = module.database.postgres_disk_name
  network         = module.networking.network_name
  subnetwork      = module.networking.subnet_name

  depends_on = [google_project_service.required_apis, module.database, module.networking]
}

module "vm_lifecycle" {
  source = "./modules/vm_lifecycle"

  project_id         = var.project_id
  region             = var.region
  zone               = var.zone
  service_account    = google_service_account.digitaltwin_sa.email
  source_bucket      = google_storage_bucket.function_source.name
  instance_template  = module.vm.instance_template_name
  slack_topic        = google_pubsub_topic.slack_webhooks.id
  vm_lifecycle_topic = google_pubsub_topic.vm_lifecycle.id

  depends_on = [google_project_service.required_apis, module.vm, module.webhook]
}

# Pub/Sub topics
resource "google_pubsub_topic" "slack_webhooks" {
  name = "slack-webhooks"

  depends_on = [google_project_service.required_apis]
}

resource "google_pubsub_topic" "vm_lifecycle" {
  name = "vm-lifecycle"

  depends_on = [google_project_service.required_apis]
}

# Cloud Scheduler for cleanup
resource "google_cloud_scheduler_job" "cleanup_inactive_vms" {
  name     = "cleanup-inactive-vms"
  schedule = "*/5 * * * *" # Every 5 minutes
  region   = var.region

  pubsub_target {
    topic_name = google_pubsub_topic.vm_lifecycle.id
    data = base64encode(jsonencode({
      action    = "cleanup"
      timestamp = timestamp()
    }))
  }

  depends_on = [google_project_service.required_apis]
}

# Monitoring - Uptime check for the VM when running
# NOTE: Commented out because the VM host is created dynamically
# After the VM starts, create this manually via GCP Console or run:
# gcloud monitoring uptime-checks create --display-name="Digital Twin Health" \
#   --http-check-path="/health" --http-check-port=8000 \
#   --resource-type=uptime-url --selected-regions=europe-central2 \
#   --http-check-use-ssl=false

# resource "google_monitoring_uptime_check_config" "digitaltwin_health" {
#   display_name = "Digital Twin Health Check"
#   timeout      = "10s"

#   http_check {
#     path         = "/health"
#     port         = "8000"
#     use_ssl      = false
#     validate_ssl = false
#   }

#   monitored_resource {
#     type = "uptime_url"
#     labels = {
#       project_id = var.project_id
#       host       = "VM_IP_HERE"  # Replace with actual VM external IP after deployment
#     }
#   }

#   depends_on = [google_project_service.required_apis]
# }
