# Digital Twin — GCP Infrastructure

Terraform configuration for the auto-scaling Digital Twin production deployment.
Project: `digitaltwin-gcp-pr`, region: `europe-central2`, zone: `europe-central2-a`.

## Architecture

```
Slack message
  → Cloud Function: slack-webhook-proxy  (HTTP, public)
  → Pub/Sub: slack-webhooks
  → Cloud Function: slack-activity-handler  (Pub/Sub, 540s timeout)
      starts VM from instance template
      polls :8000/health until ready (480s max)
      forwards original raw Slack payload to /api/v1/slack/events
  → VM: digitaltwin-instance  (e2-medium, Container-Optimized OS)
      postgres: pgvector/pgvector:pg15
      app:      gcr.io/digitaltwin-gcp-pr/digitaltwin:latest  (--network host)
      disk:     /dev/disk/by-id/google-postgres-data
                  → /mnt/stateful_partition/postgres-data/pgdata
```

## Prerequisites

- `gcloud` CLI authenticated to `digitaltwin-gcp-pr`
- Terraform ≥ 1.0
- Docker with buildx (for building amd64 images on Apple Silicon)
- All secrets created in Secret Manager (see below)

## Secrets — managed outside Terraform

**All secret values are managed manually.** Terraform only creates the secret
containers (`google_secret_manager_secret`). Never run `terraform destroy` on secrets
that hold real values — they have `prevent_destroy = true`.

| Secret name | Content |
|---|---|
| `anthropic-api-key` | Anthropic API key (`sk-ant-...`) |
| `voyage-api-key` | Voyage AI key (for `voyage-3` embeddings, 1024 dims) |
| `admin-api-key` | App admin key |
| `subject-id` | `Vasil Andrijovich` (must match `subject_id` in `dt_memory_items`) |
| `slack-bot-token` | Slack bot token (`xoxb-...`) |
| `slack-signing-secret` | Slack app signing secret |
| `slack-chat-channel-id` | Channel ID for `dt_chat` (bare `C...`, no `slack:` prefix) |
| `slack-corrections-channel-id` | Channel ID for `dt_corrections` (bare `C...`) |

Create or update a secret value:
```bash
echo -n "VALUE" | gcloud secrets versions add SECRET_NAME \
  --data-file=- --project=digitaltwin-gcp-pr
```

## First-time deployment

### 1. Build and push the container (must be amd64)

```bash
cd /path/to/DigitalTwin

# One-time buildx setup
docker buildx create --use

docker buildx build --platform linux/amd64 \
  -t gcr.io/digitaltwin-gcp-pr/digitaltwin:latest --push .
```

### 2. Create all secrets in Secret Manager

```bash
echo -n "sk-ant-..." | gcloud secrets create anthropic-api-key --data-file=- --project=digitaltwin-gcp-pr
echo -n "pa-..."     | gcloud secrets create voyage-api-key --data-file=- --project=digitaltwin-gcp-pr
echo -n "your-key"   | gcloud secrets create admin-api-key --data-file=- --project=digitaltwin-gcp-pr
echo -n "Vasil Andrijovich" | gcloud secrets create subject-id --data-file=- --project=digitaltwin-gcp-pr
echo -n "xoxb-..."   | gcloud secrets create slack-bot-token --data-file=- --project=digitaltwin-gcp-pr
echo -n "abc123..."  | gcloud secrets create slack-signing-secret --data-file=- --project=digitaltwin-gcp-pr
echo -n "C0XXXXXXX"  | gcloud secrets create slack-chat-channel-id --data-file=- --project=digitaltwin-gcp-pr
echo -n "C0YYYYYYY"  | gcloud secrets create slack-corrections-channel-id --data-file=- --project=digitaltwin-gcp-pr
```

### 3. Deploy infrastructure

```bash
cd terraform
terraform init
terraform apply -var-file=terraform.tfvars
```

### 4. Configure Slack webhook URL

Get the deployed URL:
```bash
gcloud functions describe slack-webhook-proxy \
  --project=digitaltwin-gcp-pr --region=europe-central2 \
  --format="value(httpsTrigger.url)"
```

Set it in your Slack app: **Event Subscriptions → Request URL**.

### 5. Trigger first VM and import memories

Send a Slack message to trigger VM creation. Once the VM is up:

```bash
# Export from local DB
docker exec postgres pg_dump --data-only --no-owner \
  --table=dt_raw_sources --table=dt_memory_items \
  -U digitaltwin -d digitaltwin > memory_export.sql

# Copy and import to cloud
gcloud compute scp memory_export.sql digitaltwin-instance:/tmp/ \
  --project=digitaltwin-gcp-pr --zone=europe-central2-a

gcloud compute ssh digitaltwin-instance \
  --project=digitaltwin-gcp-pr --zone=europe-central2-a \
  -- "sudo docker cp /tmp/memory_export.sql postgres:/tmp/ && \
      sudo docker exec postgres psql -U digitaltwin -d digitaltwin -f /tmp/memory_export.sql && \
      sudo docker exec postgres psql -U digitaltwin -d digitaltwin \
        -c \"UPDATE dt_memory_items SET subject_id = 'Vasil Andrijovich';\""

# Generate embeddings (voyage-3, 1024 dims) — takes ~25 min for 5815 items
# See docs/cloud_deployment_pitfalls.md for the embed.py script
```

## Ongoing operations

### Redeploy after code changes

```bash
# Rebuild image
docker buildx build --platform linux/amd64 \
  -t gcr.io/digitaltwin-gcp-pr/digitaltwin:latest --push .

# Update infrastructure (new instance template, redeploy functions)
terraform apply -var-file=terraform.tfvars

# Delete current VM so next Slack message uses the new template+image
gcloud compute instances delete digitaltwin-instance \
  --project=digitaltwin-gcp-pr --zone=europe-central2-a --quiet
```

### Check if everything is working

```bash
# Webhook proxy logs
gcloud functions logs read slack-webhook-proxy \
  --project=digitaltwin-gcp-pr --region=europe-central2 --limit=5

# VM lifecycle logs
gcloud functions logs read slack-activity-handler \
  --project=digitaltwin-gcp-pr --region=europe-central2 --limit=10

# VM startup logs
gcloud compute instances get-serial-port-output digitaltwin-instance \
  --project=digitaltwin-gcp-pr --zone=europe-central2-a \
  2>&1 | grep "startup-script:" | tail -20

# App logs
gcloud compute ssh digitaltwin-instance \
  --project=digitaltwin-gcp-pr --zone=europe-central2-a \
  -- "sudo docker logs digitaltwin --tail=30"
```

## Important implementation notes

**COS-specific constraints** (Container-Optimized OS):
- Root filesystem is read-only. Use `/mnt/stateful_partition/` for all persistent data.
- `gcloud` is not installed. Use `curl` + metadata API for Secret Manager and GCR auth.
- Docker login config must go to `DOCKER_CONFIG=/tmp/docker-config` (not `/root/.docker`).
- iptables `INPUT` policy is `DROP`. Port 8000 must be explicitly opened in startup script.

**Disk persistence:**
- The persistent disk uses `auto_delete = false` and `prevent_destroy = true`.
- Disk is detected via `/dev/disk/by-id/google-postgres-data` (stable GCP device path).
- Never use `/dev/sd*` iteration — device ordering is not guaranteed across reboots.

**Secret Manager:**
- `terraform apply` does NOT touch secret values (version resources removed from state).
- The Terraform `slack_signing_secret` variable in `terraform.tfvars` is still used to
  pass the value to the webhook proxy Cloud Function environment variable.

**Embeddings:**
- Column type: `vector(1024)`. Model: `voyage-3` (1024 dims).
- After data import, embeddings must be regenerated (they are not stored in the export).

**Slack signature:**
- The webhook proxy stores the raw request body as base64 in Pub/Sub.
- The lifecycle function forwards the exact original bytes — never re-serialised JSON.
- Re-serialising breaks the HMAC signature Slack computed over the original bytes.

**Channel IDs:**
- Secrets store bare channel IDs (e.g. `C0B0TU2JX52`).
- Startup script registers them with `slack:` prefix (e.g. `slack:C0B0TU2JX52`).
- `normalize_slack_event()` adds the `slack:` prefix — both sides must match.

See `docs/cloud_deployment_pitfalls.md` for the complete pitfall catalogue (24 issues).

## Modules

| Module | What it creates |
|---|---|
| `modules/networking` | VPC `digitaltwin-network`, subnet, firewall rules (ports 22, 80, 443, 8000) |
| `modules/database` | Persistent SSD disk `digitaltwin-postgres-data` (50 GB) |
| `modules/vm` | Instance template with COS, persistent disk attachment, startup script |
| `modules/webhook` | Cloud Function `slack-webhook-proxy` (HTTP trigger) |
| `modules/vm_lifecycle` | Cloud Functions `slack-activity-handler` + `vm-lifecycle-manager` |

## Cost estimate

| Component | Monthly cost |
|---|---|
| Persistent disk 50 GB SSD | ~$9 (always on) |
| Cloud Functions | ~$1 (per invocation volume) |
| Pub/Sub | ~$0.50 |
| VM e2-medium | ~$5–20 (only when active) |
| **Total** | **~$15–30** |
