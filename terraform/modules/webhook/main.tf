variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region"
  type        = string
}

variable "service_account" {
  description = "Service account email"
  type        = string
}

variable "source_bucket" {
  description = "Cloud Storage bucket for function source"
  type        = string
}

variable "slack_signing_secret" {
  description = "Slack signing secret"
  type        = string
  default     = ""
}

# Cloud Function source archive
data "archive_file" "webhook_source" {
  type        = "zip"
  output_path = "/tmp/webhook-source.zip"
  source_dir  = "webhook_proxy"

  depends_on = [local_file.webhook_proxy_source]
}

# Create the webhook proxy source files
resource "local_file" "webhook_proxy_source" {
  for_each = {
    "main.py" = <<EOF
import json
import logging
import hmac
import hashlib
import os
from google.cloud import pubsub_v1
import google.auth
from flask import Request, abort

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

publisher = pubsub_v1.PublisherClient()
PROJECT_ID = google.auth.default()[1]

# Retrieve signing secret from Secret Manager
from google.cloud import secretmanager_v1 as secretmanager
secret_client = secretmanager.SecretManagerServiceClient()
secret_name = f"projects/{PROJECT_ID}/secrets/slack-signing-secret/versions/latest"
response = secret_client.access_secret_version(request={"name": secret_name})
SLACK_SIGNING_SECRET = response.payload.data.decode("UTF-8")

def verify_slack_signature(request: Request, signing_secret: str) -> bool:
    """Verify Slack webhook signature"""
    if not signing_secret:
        logger.warning("Slack signing secret not configured - skipping verification")
        return True

    timestamp = request.headers.get('X-Slack-Request-Timestamp')
    signature = request.headers.get('X-Slack-Signature')

    if not timestamp or not signature:
        return False

    # Create the basestring
    body = request.get_data()
    basestring = f"v0:{timestamp}:{body.decode('utf-8')}"

    # Create the expected signature
    expected_signature = hmac.new(
        signing_secret.encode('utf-8'),
        basestring.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    expected_signature = f"v0={expected_signature}"

    return hmac.compare_digest(expected_signature, signature)

def slack_webhook_proxy(request: Request):
    """Receive Slack webhooks and forward to Pub/Sub"""

    # Verify Slack signature if configured
    if not verify_slack_signature(request, SLACK_SIGNING_SECRET):
        logger.warning("Invalid Slack signature")
        abort(401)

    # Parse webhook payload
    payload = request.get_json()

    if payload.get('type') == 'url_verification':
        return {'challenge': payload['challenge']}

    # Forward to Pub/Sub including the raw body bytes (base64) so the VM
    # can forward the exact original body — re-serialising JSON would break
    # the Slack signature which was computed over the original raw bytes.
    import base64 as _b64
    topic_path = publisher.topic_path(PROJECT_ID, 'slack-webhooks')
    message_data = {
        'payload': payload,
        'raw_body': _b64.b64encode(request.get_data()).decode('utf-8'),
        'slack_timestamp': request.headers.get('X-Slack-Request-Timestamp', ''),
        'slack_signature': request.headers.get('X-Slack-Signature', ''),
    }
    data = json.dumps(message_data).encode('utf-8')

    publisher.publish(topic_path, data)
    logger.info(f"Forwarded Slack webhook to Pub/Sub")

    # Acknowledge immediately (don't wait for processing)
    return {'status': 'ok'}
EOF

    "requirements.txt" = <<EOF
google-cloud-pubsub==2.18.0
flask==2.3.0
google-cloud-secret-manager
EOF
  }

  filename = "webhook_proxy/${each.key}"
  content  = each.value
}

# Upload source to Cloud Storage
resource "google_storage_bucket_object" "webhook_source" {
  name   = "webhook-proxy-source-${data.archive_file.webhook_source.output_md5}.zip"
  bucket = var.source_bucket
  source = data.archive_file.webhook_source.output_path
}

# Cloud Function
resource "google_cloudfunctions_function" "webhook_proxy" {
  name    = "slack-webhook-proxy"
  runtime = "python312"
  region  = var.region

  source_archive_bucket = var.source_bucket
  source_archive_object = google_storage_bucket_object.webhook_source.name

  entry_point  = "slack_webhook_proxy"
  trigger_http = true

  service_account_email = var.service_account

  # No environment variables needed - secrets retrieved from Secret Manager
}

# Allow unauthenticated access for Slack webhooks
# In production, consider using API Gateway for additional security
resource "google_cloudfunctions_function_iam_member" "webhook_invoker" {
  project        = var.project_id
  region         = var.region
  cloud_function = google_cloudfunctions_function.webhook_proxy.name

  role   = "roles/cloudfunctions.invoker"
  member = "allUsers"
}

# Outputs
output "function_name" {
  description = "Cloud Function name"
  value       = google_cloudfunctions_function.webhook_proxy.name
}

output "function_url" {
  description = "Cloud Function HTTPS URL"
  value       = google_cloudfunctions_function.webhook_proxy.https_trigger_url
}
