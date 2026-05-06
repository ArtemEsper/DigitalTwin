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

variable "source_bucket" {
  description = "Cloud Storage bucket for function source"
  type        = string
}

variable "instance_template" {
  description = "Compute Engine instance template name"
  type        = string
}

variable "slack_topic" {
  description = "Pub/Sub topic for Slack webhooks"
  type        = string
}

variable "vm_lifecycle_topic" {
  description = "Pub/Sub topic for VM lifecycle management"
  type        = string
}

# Cloud Function source archive
data "archive_file" "vm_lifecycle_source" {
  type        = "zip"
  output_path = "/tmp/vm-lifecycle-source.zip"
  source_dir  = "vm_lifecycle"

  depends_on = [local_file.vm_lifecycle_source]
}

# Create the VM lifecycle manager source files
resource "local_file" "vm_lifecycle_source" {
  for_each = {
    "main.py" = <<EOF
import base64
import json
import logging
import os
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from google.cloud import compute_v1, pubsub_v1
from google.api_core.exceptions import NotFound
import google.auth
from flask import Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROJECT_ID = google.auth.default()[1]
ZONE = "europe-central2-a"  # Use the configured zone

compute_client = compute_v1.InstancesClient()
instance_client = compute_v1.InstanceTemplatesClient()

INACTIVITY_THRESHOLD = timedelta(minutes=int(os.environ.get('INACTIVITY_TIMEOUT_MINUTES', '5')))

def get_instance_template_name():
    """Get the instance template name from environment or use default"""
    return os.environ.get('INSTANCE_TEMPLATE', 'digitaltwin')

def check_vm_exists(instance_name: str) -> bool:
    """Check if a VM instance exists"""
    try:
        request = compute_v1.GetInstanceRequest(
            project=PROJECT_ID,
            zone=ZONE,
            instance=instance_name
        )
        compute_client.get(request)
        return True
    except NotFound:
        return False
    except Exception as e:
        logger.error(f"Error checking VM existence: {e}")
        return False

def start_vm(instance_name: str) -> bool:
    """Start a VM instance, waking it up if stopped or creating it if absent."""
    try:
        request = compute_v1.GetInstanceRequest(
            project=PROJECT_ID,
            zone=ZONE,
            instance=instance_name,
        )
        try:
            instance = compute_client.get(request)
            if instance.status == 'RUNNING':
                logger.info(f"VM {instance_name} is already running")
                return True
            # Wake up a stopped/terminated instance instead of recreating it
            logger.info(f"VM {instance_name} is {instance.status}, waking it up")
            operation = compute_client.start(
                project=PROJECT_ID, zone=ZONE, instance=instance_name
            )
            operation.result()
            logger.info(f"Woke up VM: {instance_name}")
            return True
        except NotFound:
            pass  # Instance doesn't exist yet — create it below

        # Create instance from template
        template_name = get_instance_template_name()
        template_request = compute_v1.GetInstanceTemplateRequest(
            project=PROJECT_ID,
            instance_template=template_name
        )
        template = instance_client.get(template_request)

        instance_resource = compute_v1.Instance()
        instance_resource.name = instance_name

        insert_request = compute_v1.InsertInstanceRequest(
            project=PROJECT_ID,
            zone=ZONE,
            instance_resource=instance_resource,
            source_instance_template=template.self_link,
        )

        operation = compute_client.insert(insert_request)
        operation.result()

        logger.info(f"Created and started VM: {instance_name}")
        return True

    except Exception as e:
        logger.error(f"Error starting VM {instance_name}: {e}")
        return False

def stop_vm(instance_name: str) -> bool:
    """Stop a VM instance"""
    try:
        if not check_vm_exists(instance_name):
            logger.info(f"VM {instance_name} does not exist")
            return True

        request = compute_v1.StopInstanceRequest(
            project=PROJECT_ID,
            zone=ZONE,
            instance=instance_name
        )

        operation = compute_client.stop(request)
        operation.result()  # Wait for completion

        logger.info(f"Stopped VM: {instance_name}")
        return True

    except Exception as e:
        logger.error(f"Error stopping VM {instance_name}: {e}")
        return False

def update_last_activity(instance_name: str) -> None:
    """Stamp the current UTC time into the VM's 'last-activity' metadata key."""
    try:
        instance = compute_client.get(
            project=PROJECT_ID, zone=ZONE, instance=instance_name
        )
        existing_items = [
            item for item in instance.metadata.items
            if item.key != "last-activity"
        ]
        existing_items.append(
            compute_v1.Items(
                key="last-activity",
                value=datetime.now(timezone.utc).isoformat(),
            )
        )
        compute_client.set_metadata(
            project=PROJECT_ID,
            zone=ZONE,
            instance=instance_name,
            metadata_resource=compute_v1.Metadata(
                fingerprint=instance.metadata.fingerprint,
                items=existing_items,
            ),
        )
        logger.info(f"Updated last-activity metadata on {instance_name}")
    except Exception as e:
        logger.error(f"Error updating last-activity on {instance_name}: {e}")

def cleanup_inactive_vms():
    """Stop VMs that have been inactive longer than INACTIVITY_THRESHOLD."""
    try:
        request = compute_v1.AggregatedListInstancesRequest(
            project=PROJECT_ID,
            filter='labels.app=digitaltwin',
        )
        instances = compute_client.aggregated_list(request)
        now = datetime.now(timezone.utc)

        for zone, instance_list in instances:
            if not instance_list.instances:
                continue
            for instance in instance_list.instances:
                if instance.status != 'RUNNING':
                    continue

                last_activity_str = next(
                    (item.value for item in instance.metadata.items
                     if item.key == "last-activity"),
                    None,
                )

                if last_activity_str is None:
                    creation_str = instance.creation_timestamp
                    last_activity = datetime.fromisoformat(creation_str)
                    logger.info(
                        f"{instance.name}: no last-activity metadata, "
                        f"falling back to creation time {creation_str}"
                    )
                else:
                    last_activity = datetime.fromisoformat(last_activity_str)

                idle_duration = now - last_activity
                logger.info(
                    f"{instance.name}: idle for {idle_duration} "
                    f"(threshold {INACTIVITY_THRESHOLD})"
                )

                if idle_duration > INACTIVITY_THRESHOLD:
                    logger.info(
                        f"Stopping inactive VM {instance.name} "
                        f"(idle {idle_duration})"
                    )
                    stop_vm(instance.name)

        logger.info("VM cleanup check completed")

    except Exception as e:
        logger.error(f"Error during VM cleanup: {e}")

def get_vm_external_ip(instance_name: str) -> str:
    """Return the external IP of a running VM instance."""
    try:
        request = compute_v1.GetInstanceRequest(
            project=PROJECT_ID,
            zone=ZONE,
            instance=instance_name,
        )
        instance = compute_client.get(request)
        return instance.network_interfaces[0].access_configs[0].nat_i_p
    except Exception as e:
        logger.error(f"Error getting VM IP: {e}")
        return ""


def wait_for_vm_ready(vm_ip: str, timeout: int = 480) -> bool:
    """Poll the health endpoint until the app is up or timeout is reached."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://{vm_ip}:8000/health", timeout=5)
            logger.info(f"VM at {vm_ip} is ready")
            return True
        except Exception:
            time.sleep(10)
    logger.error(f"VM at {vm_ip} did not become ready within {timeout}s")
    return False


def forward_to_vm(vm_ip: str, raw_body: bytes, slack_timestamp: str, slack_signature: str) -> bool:
    """Forward the Slack event to the FastAPI app using the original raw body."""
    req = urllib.request.Request(
        f"http://{vm_ip}:8000/api/v1/slack/events",
        data=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Slack-Request-Timestamp": slack_timestamp,
            "X-Slack-Signature": slack_signature,
        },
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        logger.info("Slack event forwarded to VM successfully")
        return True
    except Exception as e:
        logger.error(f"Error forwarding event to VM: {e}")
        return False


def handle_slack_webhook(event, context):
    """Handle Slack webhook events: start VM then forward the event to the app."""
    try:
        # Parse the Pub/Sub message (data is base64-encoded in Cloud Functions Gen 1)
        pubsub_message = json.loads(base64.b64decode(event['data']).decode('utf-8'))

        # Support both new format (with headers) and old format (raw payload)
        payload = pubsub_message.get('payload', pubsub_message)
        slack_timestamp = pubsub_message.get('slack_timestamp', '')
        slack_signature = pubsub_message.get('slack_signature', '')
        raw_body = base64.b64decode(pubsub_message['raw_body']) if 'raw_body' in pubsub_message else json.dumps(payload).encode('utf-8')

        logger.info(f"Received Slack webhook: {payload.get('type', 'unknown')}")

        instance_name = "digitaltwin-instance"

        if not start_vm(instance_name):
            logger.error("Failed to start VM")
            return

        vm_ip = get_vm_external_ip(instance_name)
        if not vm_ip:
            logger.error("Could not determine VM external IP")
            return

        if not wait_for_vm_ready(vm_ip):
            logger.error("VM did not become ready in time")
            return

        if forward_to_vm(vm_ip, raw_body, slack_timestamp, slack_signature):
            update_last_activity(instance_name)

    except Exception as e:
        logger.error(f"Error handling Slack webhook: {e}")

def handle_vm_lifecycle(event, context):
    """Handle VM lifecycle management events"""
    try:
        # Parse the Pub/Sub message (data is base64-encoded in Cloud Functions Gen 1)
        pubsub_message = json.loads(base64.b64decode(event['data']).decode('utf-8'))
        action = pubsub_message.get('action')

        logger.info(f"Received VM lifecycle action: {action}")

        if action == 'cleanup':
            cleanup_inactive_vms()
        elif action == 'start':
            instance_name = pubsub_message.get('instance_name', 'digitaltwin-instance')
            start_vm(instance_name)
        elif action == 'stop':
            instance_name = pubsub_message.get('instance_name', 'digitaltwin-instance')
            stop_vm(instance_name)
        else:
            logger.warning(f"Unknown action: {action}")

    except Exception as e:
        logger.error(f"Error handling VM lifecycle event: {e}")

# For HTTP trigger (if needed for testing)
def vm_lifecycle_manager(request: Request):
    """HTTP endpoint for VM lifecycle management (for testing)"""
    try:
        data = request.get_json()
        action = data.get('action', 'status')

        if action == 'start':
            instance_name = data.get('instance_name', 'digitaltwin-instance')
            success = start_vm(instance_name)
            return {'status': 'started' if success else 'error'}
        elif action == 'stop':
            instance_name = data.get('instance_name', 'digitaltwin-instance')
            success = stop_vm(instance_name)
            return {'status': 'stopped' if success else 'error'}
        elif action == 'cleanup':
            cleanup_inactive_vms()
            return {'status': 'cleanup_completed'}
        else:
            return {'status': 'unknown_action'}

    except Exception as e:
        logger.error(f"Error in VM lifecycle manager: {e}")
        return {'status': 'error', 'message': str(e)}
EOF

    "requirements.txt" = <<EOF
google-cloud-compute==1.18.0
google-cloud-pubsub==2.18.0
flask==2.3.0
EOF
  }

  filename = "vm_lifecycle/${each.key}"
  content  = each.value
}

# Upload source to Cloud Storage
resource "google_storage_bucket_object" "vm_lifecycle_source" {
  name   = "vm-lifecycle-source-${data.archive_file.vm_lifecycle_source.output_md5}.zip"
  bucket = var.source_bucket
  source = data.archive_file.vm_lifecycle_source.output_path
}

# Cloud Function for Slack webhook handling
resource "google_cloudfunctions_function" "slack_activity_handler" {
  name    = "slack-activity-handler"
  runtime = "python312"
  region  = var.region

  source_archive_bucket = var.source_bucket
  source_archive_object = google_storage_bucket_object.vm_lifecycle_source.name

  entry_point = "handle_slack_webhook"
  timeout     = 540

  service_account_email = var.service_account

  environment_variables = {
    PROJECT_ID        = var.project_id
    INSTANCE_TEMPLATE = var.instance_template
  }

  event_trigger {
    event_type = "google.pubsub.topic.publish"
    resource   = var.slack_topic
  }

  depends_on = [google_cloudfunctions_function.vm_lifecycle_manager]
}

# Cloud Function for VM lifecycle management
resource "google_cloudfunctions_function" "vm_lifecycle_manager" {
  name    = "vm-lifecycle-manager"
  runtime = "python312"
  region  = var.region

  source_archive_bucket = var.source_bucket
  source_archive_object = google_storage_bucket_object.vm_lifecycle_source.name

  entry_point = "handle_vm_lifecycle"

  service_account_email = var.service_account

  environment_variables = {
    PROJECT_ID        = var.project_id
    INSTANCE_TEMPLATE = var.instance_template
  }

  event_trigger {
    event_type = "google.pubsub.topic.publish"
    resource   = var.vm_lifecycle_topic
  }
}

# Outputs
output "slack_activity_handler_name" {
  description = "Slack activity handler Cloud Function name"
  value       = google_cloudfunctions_function.slack_activity_handler.name
}

output "vm_lifecycle_manager_name" {
  description = "VM lifecycle manager Cloud Function name"
  value       = google_cloudfunctions_function.vm_lifecycle_manager.name
}
