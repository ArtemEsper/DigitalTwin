# Terraform GCP Infrastructure - Fixes Applied

## Issues Fixed

### 1. ✅ Cloud Function Artifact Registry Permission
**Error**: `Unable to retrieve the repository metadata... Ensure that the Cloud Functions service account has 'artifactregistry.repositories.list' and 'artifactregistry.repositories.get' permissions`

**Root Cause**: Service account didn't have permissions to access the artifact registry where Cloud Functions stores its compiled code.

**Solution**: 
- Added `roles/artifactregistry.reader` IAM role to service account
- Added `roles/cloudfunctions.serviceAgent` to allow the service account to run as a Cloud Function
- Enabled `artifactregistry.googleapis.com` and `monitoring.googleapis.com` APIs

### 2. ✅ Uptime Check Invalid Host
**Error**: `uptime_url check has malformed host`

**Root Cause**: Uptime check was using a placeholder hostname ("placeholder") which is invalid for monitoring

**Solution**: 
- Commented out the uptime check resource
- Added instructions to create it manually after VM starts with a real external IP
- Provided gcloud command to create the uptime check post-deployment

## Files Modified

1. **terraform/main.tf**:
   - ✅ Added missing APIs: `artifactregistry.googleapis.com`, `monitoring.googleapis.com`
   - ✅ Added missing IAM roles: `roles/artifactregistry.reader`, `roles/cloudfunctions.serviceAgent`
   - ✅ Commented out problematic uptime check
   - ✅ Added `slack_signing_secret` to webhook module call

## Current Status

✅ **Terraform Configuration**: Valid
✅ **APIs**: All 10 required APIs enabled
✅ **Service Account**: Created with 9 IAM roles
✅ **Networking**: VPC, subnets, firewall rules ready
✅ **Database**: Persistent disk created and protected from deletion
✅ **Cloud Function**: Ready to be deployed
✅ **Pub/Sub**: Topics created
✅ **Scheduler**: Cleanup job configured

## What Will Deploy

This Terraform configuration will create:

```
GCP Infrastructure: dbt-practice-esper
├── Service Account: digitaltwin-service@... (9 IAM roles)
├── VPC Network: digitaltwin-network
├── Subnet: digitaltwin-subnet with 10.0.0.0/24
├── Firewall Rules: SSH, HTTP, HTTPS, internal traffic
├── Persistent Disk: postgres-data (50GB SSD, protected)
├── Cloud Storage: Bucket for Cloud Function source
├── Cloud Function: slack-webhook-proxy
│   - Python 3.12 runtime
│   - HTTP trigger (webhook)
│   - Slack signature verification
│   - Pub/Sub publishing
├── Pub/Sub Topics:
│   - slack-webhooks (webhook events)
│   - vm-lifecycle (VM management)
├── Cloud Scheduler:
│   - cleanup-inactive-vms (every 5 minutes)
└── Instance Template:
    - Machine: e2-medium
    - OS: Container-Optimized OS
    - startup-script: Mounts disk, runs PostgreSQL, prepares for FastAPI
```

## Next Steps: Deploy the Infrastructure

### Option 1: Re-run with Updated Configuration (Recommended)

Clean up the previous failed partial resources and deploy fresh:

```bash
cd /Users/macbook/Documents/GitHub/DigitalTwin/terraform

# Option A: Clean and redeploy
terraform destroy -var-file=terraform.tfvars -auto-approve
terraform apply -var-file=terraform.tfvars

# Option B: Just apply (will skip existing resources)
terraform apply -var-file=terraform.tfvars
```

### Option 2: Check Current Partial Deployment

```bash
# See what Terraform thinks exists
terraform show

# List actual GCP resources
gcloud compute instances templates list
gcloud functions list
gcloud pubsub topics list
gcloud compute disks list
```

## Expected Deployment Time

- First run: 5-8 minutes (APIs enabling + resources creation)
- Subsequent runs: < 1 minute (no changes)

## Cost Estimate

Monthly costs with this configuration:
- **Persistent Disk (50GB SSD)**: ~$2/month (always running)
- **Cloud Function invocations**: ~$0.50-2/month
- **Pub/Sub**: ~$0.50/month
- **Cloud Scheduler**: ~$0.10/month
- **Compute Engine VM**: $5-20/month (only when active processing Slack messages)
- **Total**: $8-25/month (vs $50+ for always-on VM)

## Post-Deployment Checklist

After `terraform apply` succeeds:

- [ ] Get webhook URL: `terraform output webhook_proxy_url`
- [ ] Update Slack app Events API URL
- [ ] Create manual uptime check (see commented code in main.tf)
- [ ] SSH into VM when it starts: `gcloud compute ssh digitaltwin-vm-XXXXX --zone=europe-central2-a`
- [ ] Verify PostgreSQL is running: `docker ps`
- [ ] Run Alembic migrations: `alembic upgrade head`
- [ ] Start FastAPI app (containerized or direct)

## Troubleshooting

### If deployment still fails:

```bash
# Check service account permissions
gcloud projects get-iam-policy dbt-practice-esper \
  --flatten="bindings[].members" \
  --filter="members:digitaltwin-service@*"

# Check enabled APIs
gcloud services list --enabled

# Check Cloud Function logs
gcloud functions logs read slack-webhook-proxy \
  --region=europe-central2 \
  --limit 50
```

### If webhook creation fails:

```bash
# Check Cloud Storage bucket exists
gcloud storage buckets list

# Re-upload function source
gcloud functions deploy slack-webhook-proxy \
  --region=europe-central2 \
  --runtime=python312 \
  --trigger-http \
  --source=webhook_proxy/ \
  --entry-point=slack_webhook_proxy
```

## Files in Terraform

- `terraform/main.tf` - ✅ Fixed (10 APIs, 9 IAM roles, uptime check commented)
- `terraform/variables.tf` - All variables defined
- `terraform/outputs.tf` - Resource outputs and manual steps
- `terraform/terraform.tfvars` - ✅ Your configuration (project_id, slack_signing_secret, etc.)
- `terraform/modules/networking/` - VPC, subnets, firewall
- `terraform/modules/database/` - Persistent disk
- `terraform/modules/webhook/` - Cloud Function
- `terraform/modules/vm/` - VM instance template
- `terraform/scripts/startup.sh` - VM initialization script
