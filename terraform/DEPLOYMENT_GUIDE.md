# Terraform Deployment Checklist & Instructions

## Current Configuration Status

✅ **Project ID**: Updated to `dbt-practice-esper`
✅ **Region/Zone**: Set to `europe-central2` / `europe-central2-a`
✅ **GCP Permissions**: You have `roles/editor` (sufficient for deployment)
❌ **Slack Signing Secret**: Still needs to be updated

## Step 1: Get Your Slack Signing Secret

1. Go to: https://api.slack.com/apps
2. Select your Digital Twin app
3. Go to **Basic Information** section
4. Scroll down to **App Credentials**
5. Copy the **Signing Secret** (looks like: `abc123def456...`)

## Step 2: Update terraform.tfvars

Replace the placeholder in your terraform.tfvars:

```hcl
slack_signing_secret = "your-actual-slack-signing-secret-here"
```

With your actual Slack signing secret from Step 1.

## Step 3: Verify Your Configuration

```bash
cd /Users/macbook/Documents/GitHub/DigitalTwin/terraform

# Show current configuration
terraform plan -var-file=terraform.tfvars | head -30
```

Expected to see resources being created for:
- Google Service Account
- Cloud Storage Bucket
- VPC Network
- Persistent Disk
- Cloud Function
- Pub/Sub Topics
- Cloud Scheduler

## Step 4: Deploy (When Ready)

```bash
# Plan the deployment (review changes)
terraform plan -var-file=terraform.tfvars

# Apply the deployment (creates all resources)
terraform apply -var-file=terraform.tfvars
```

## Step 5: Post-Deployment

After `terraform apply` completes successfully:

1. **Get the webhook URL** (Terraform output):
   ```bash
   terraform output webhook_proxy_url
   ```

2. **Update Slack App webhook URL**:
   - Go to https://api.slack.com/apps → Your App → Event Subscriptions
   - Enable Events → Request URL
   - Paste the URL from step 1
   - Click "Save Changes"

3. **Wait for Slack verification** (should say "Verified")

## Troubleshooting

### If you see "Project not found" error:
```bash
# Verify you're using the correct project
gcloud config get-value project
# Should output: dbt-practice-esper

# If not, set it:
gcloud config set project dbt-practice-esper
```

### If you see permission errors:
```bash
# Check your current account
gcloud auth list

# If using wrong account, switch:
gcloud config set account chumachenko.a@gmail.com

# Verify roles in project
gcloud projects get-iam-policy dbt-practice-esper --flatten="bindings[].members" --filter="members:*@*.com" --format=table
```

### If you need to clean up failed resources:
```bash
# Destroy all created resources
terraform destroy -var-file=terraform.tfvars
```

## Cost Estimate

After deployment, typical monthly costs:
- **Persistent Disk (50GB SSD)**: ~$2/month (always running)
- **Cloud Function**: ~$0.50-2/month (per invocation)
- **Pub/Sub**: ~$0.50/month (low volume)
- **Compute Engine VM**: ~$5-20/month (only when active)
- **Total**: $8-25/month vs $50+ for always-on

## Next Steps After Deployment

1. SSH into the VM when it starts:
   ```bash
   gcloud compute ssh digitaltwin-vm \
     --project=dbt-practice-esper \
     --zone=europe-central2-a
   ```

2. Check PostgreSQL is running:
   ```bash
   docker ps
   docker logs postgres
   ```

3. Run Alembic migrations:
   ```bash
   # From your app directory
   alembic upgrade head
   ```

4. Start the Digital Twin FastAPI app (containerized or directly)

## Support

For Terraform documentation: https://registry.terraform.io/providers/hashicorp/google/latest/docs
For GCP troubleshooting: https://cloud.google.com/docs/troubleshoot
