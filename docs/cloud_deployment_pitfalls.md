# GCP Cloud Deployment — Pitfalls & Solutions

A full record of every non-obvious problem encountered during the first GCP deployment
of Digital Twin (2026-05-06). This document exists so the system can be rebuilt from
scratch without re-discovering each issue.

---

## Architecture (working state)

```
Slack message
  → Cloud Function: slack-webhook-proxy  (HTTP trigger, public)
      verifies Slack signature
      publishes {payload, raw_body, slack_timestamp, slack_signature} to Pub/Sub
  → Cloud Function: slack-activity-handler  (Pub/Sub trigger, 540s timeout)
      starts VM from instance template
      polls http://<vm-ip>:8000/health every 10s (up to 480s)
      forwards raw_body + original Slack headers to /api/v1/slack/events
  → VM: digitaltwin-instance
      pgvector/pgvector:pg15 postgres container
      gcr.io/<project>/digitaltwin:latest app container (--network host)
      iptables rule: port 8000 open
      persistent disk: /dev/disk/by-id/google-postgres-data
        → /mnt/stateful_partition/postgres-data/pgdata
```

Key GCP resources:
- Project: `digitaltwin-gcp-pr`, zone: `europe-central2-a`
- Webhook URL: `https://europe-central2-digitaltwin-gcp-pr.cloudfunctions.net/slack-webhook-proxy`
- Container: `gcr.io/digitaltwin-gcp-pr/digitaltwin:latest`
- Persistent disk: `digitaltwin-postgres-data` (50 GB SSD, `prevent_destroy = true`)

---

## Pitfall 1: COS has a read-only root filesystem

**Symptom:** `mkdir: cannot create directory '/mnt/postgres-data': Read-only file system`

**Cause:** Container-Optimized OS mounts `/` read-only. You cannot create directories
under `/mnt` directly.

**Fix:** Use `/mnt/stateful_partition/postgres-data` — the stateful partition is the
only writable persistent location on COS.

---

## Pitfall 2: `postgres:15` image does not include pgvector

**Symptom:** `CREATE EXTENSION IF NOT EXISTS vector` fails, container crashes in a
restart loop.

**Fix:** Use `pgvector/pgvector:pg15` instead of `postgres:15`.

---

## Pitfall 3: PostgreSQL refuses to initialise into a disk mount point

**Symptom:**
```
initdb: error: directory "/var/lib/postgresql/data" exists but is not empty
initdb: detail: It contains a lost+found directory, perhaps due to it being a mount point.
```

**Cause:** When you mount an ext4 disk directly as the PostgreSQL data directory, the
`lost+found` directory from the filesystem makes Postgres refuse to initialise.

**Fix:** Mount the disk at the parent path and use a subdirectory as the actual data
directory:
```
docker volume: /mnt/stateful_partition/postgres-data/pgdata → /var/lib/postgresql/data
```
The `lost+found` lives at the mount point level, not inside `pgdata`.

---

## Pitfall 4: `gcloud` is not available on Container-Optimized OS

**Symptom:** Secrets retrieved as empty string; validation fails with
`ERROR: ANTHROPIC_API_KEY not set in Secret Manager`.

**Cause:** COS is a minimal OS. `gcloud` is not installed. The startup script used
`gcloud secrets versions access` with `2>/dev/null || echo ""` which silently returned
empty string.

**Fix:** Use `curl` against the Secret Manager REST API with the VM's metadata token:
```bash
SM_TOKEN=$(curl -sf -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

fetch_secret() {
  curl -sf -H "Authorization: Bearer $SM_TOKEN" \
    "https://secretmanager.googleapis.com/v1/projects/$PROJECT_ID/secrets/$1/versions/latest:access" \
    | python3 -c "import sys,json,base64; print(base64.b64decode(json.load(sys.stdin)['payload']['data']).decode())" 2>/dev/null \
    || echo "${2:-}"
}
```

---

## Pitfall 5: Docker login writes to read-only `/root/.docker`

**Symptom:** `Error saving credentials: mkdir /root/.docker: read-only file system`

**Cause:** COS root filesystem is read-only. Docker login tries to write credentials
to `/root/.docker/config.json`.

**Fix:** Point `DOCKER_CONFIG` to a writable directory before login:
```bash
export DOCKER_CONFIG=/tmp/docker-config
mkdir -p $DOCKER_CONFIG
echo "$GCR_TOKEN" | docker login -u oauth2accesstoken --password-stdin https://gcr.io
```
All subsequent `docker pull` and `docker run` calls in the same script will use this
config because `DOCKER_CONFIG` is inherited.

---

## Pitfall 6: Docker image built on Apple Silicon (arm64) runs on amd64 VM

**Symptom:**
```
WARNING: The requested image's platform (linux/arm64/v8) does not match
the detected host platform (linux/amd64/v3)
```
Container starts but immediately crashes/restarts.

**Fix:** Always build with `--platform linux/amd64` when pushing to GCR for GCP VMs:
```bash
docker buildx build --platform linux/amd64 \
  -t gcr.io/<project>/digitaltwin:latest --push .
```

---

## Pitfall 7: `alembic.ini` and migrations not copied into Docker image

**Symptom:** `FAILED: No config file 'alembic.ini' found` when running migrations
inside the container.

**Cause:** The Dockerfile only copied `src/` — `alembic/` and `alembic.ini` were
omitted.

**Fix:** Add to Dockerfile:
```dockerfile
COPY alembic/ ./alembic/
COPY alembic.ini .
```

---

## Pitfall 8: DATABASE_URL scheme must be `postgresql+asyncpg://`

**Symptom:** `ModuleNotFoundError: No module named 'psycopg2'` during migrations;
FastAPI app crashes on startup.

**Cause:** Startup script passed `DATABASE_URL="postgresql://..."`. SQLAlchemy defaults
to psycopg2 for `postgresql://`. The app uses asyncpg and has no psycopg2 installed.

**Fix:**
```bash
-e DATABASE_URL="postgresql+asyncpg://digitaltwin:changeme@localhost:5432/digitaltwin"
```

---

## Pitfall 9: Docker networking — `localhost` inside container ≠ host machine

**Symptom:** App can't connect to PostgreSQL running in a sibling container.

**Cause:** Without `--network host`, each Docker container has its own network
namespace. `localhost` inside the app container is the container itself, not the host.

**Fix:** Run the app container with `--network host`:
```bash
docker run --network host ...
```
PostgreSQL (also `--network host` or port-published) is reachable at `localhost:5432`.

---

## Pitfall 10: Slack signature verification fails when JSON is re-serialised

**Symptom:** App returns `403 Forbidden` on every forwarded message. Slack's HMAC
signature was computed over the original raw bytes; re-serialising with `json.dumps()`
produces different bytes.

**Fix:** The webhook proxy stores the raw body as base64 in the Pub/Sub message. The
lifecycle function forwards those exact bytes — never re-serialised JSON:
```python
# webhook proxy
message_data = {
    'payload': payload,
    'raw_body': base64.b64encode(request.get_data()).decode('utf-8'),
    'slack_timestamp': request.headers.get('X-Slack-Request-Timestamp', ''),
    'slack_signature': request.headers.get('X-Slack-Signature', ''),
}
# vm lifecycle forwarder
raw_body = base64.b64decode(pubsub_message['raw_body'])
req = urllib.request.Request(url, data=raw_body, headers={...original Slack headers...})
```

---

## Pitfall 11: channel_id must include the `slack:` prefix

**Symptom:** `Ignoring message from unconfigured Slack channel C0B0TU2JX52` even
though the channel is registered in the database.

**Cause:** `normalize_slack_event()` in `slack_adapter.py` sets:
```python
channel_id=f"slack:{channel_id}"
```
But the channel was registered without the prefix (bare `C0B0TU2JX52`).

**Fix:** Register channels with the `slack:` prefix:
```python
channel_id="slack:C0B0TU2JX52"
```
The startup script's channel registration script uses `"slack:$SLACK_CHAT_CHANNEL_ID"`.

---

## Pitfall 12: COS iptables INPUT chain has `policy DROP`

**Symptom:** Health check never passes — `curl http://<vm-ip>:8000/health` times out
from Cloud Functions, but `curl http://localhost:8000/health` works inside the VM.

**Cause:** COS sets iptables `INPUT` policy to `DROP` by default. Only ports 22 (SSH),
ICMP, and `RELATED,ESTABLISHED` traffic are allowed. Port 8000 is not in the INPUT
chain even though the GCP VPC firewall allows it.

**Fix:** Add an iptables rule early in the startup script:
```bash
sudo iptables -A INPUT -p tcp --dport 8000 -j ACCEPT
```

---

## Pitfall 13: VM instance template uses `default` VPC; firewall rules on custom VPC

**Symptom:** Port 8000 still unreachable externally despite correct GCP firewall rules.

**Cause:** The instance template had `network = "default"`. All custom firewall rules
(including the one allowing port 8000) were on `digitaltwin-network`. VPC firewall
rules only apply to instances on that same VPC.

**Fix:** Update the instance template to use the custom network:
```hcl
network_interface {
  network    = var.network     # "digitaltwin-network"
  subnetwork = var.subnetwork  # "digitaltwin-subnet"
  access_config {}
}
```

---

## Pitfall 14: SSH firewall rule targets `ssh` tag; VM only has `digitaltwin` tag

**Symptom:** SSH hangs at "Waiting for SSH key to propagate".

**Fix:** Add `digitaltwin` to the SSH firewall rule's target tags:
```hcl
target_tags = ["ssh", "digitaltwin"]
```

---

## Pitfall 15: `source_instance_template` on wrong object in Compute API

**Symptom:** VM creation returns 400; template is ignored; instance created without
correct configuration.

**Cause:** `source_instance_template` is a query parameter on `InsertInstanceRequest`,
not a field on the `Instance` resource. Setting it on `Instance` is silently ignored.

**Fix:**
```python
request = compute_v1.InsertInstanceRequest(
    project=PROJECT_ID,
    zone=ZONE,
    instance_resource=instance_resource,
    source_instance_template=template.self_link,  # ← here, not on instance_resource
)
```

---

## Pitfall 16: Pub/Sub message data is base64-encoded in Cloud Functions Gen 1

**Symptom:** `AttributeError: 'str' object has no attribute 'decode'` in the activity
handler function.

**Cause:** In Cloud Functions Gen 1, `event['data']` is a base64-encoded **string**,
not bytes. Calling `.decode('utf-8')` on a string raises `AttributeError`.

**Fix:**
```python
import base64
pubsub_message = json.loads(base64.b64decode(event['data']).decode('utf-8'))
```

---

## Pitfall 17: `nat_ip` vs `nat_i_p` in google-cloud-compute Python SDK

**Symptom:** `Unknown field for AccessConfig: nat_ip` when trying to get the VM's
external IP.

**Cause:** The proto-plus Python SDK converts camelCase `natIP` to snake_case
`nat_i_p` (each capital letter gets an underscore prefix).

**Fix:**
```python
return instance.network_interfaces[0].access_configs[0].nat_i_p
```

---

## Pitfall 18: Instance template name changes on every `terraform apply`

**Symptom:** Cloud Function fails with `404 instance template 'digitaltwin' not found`
or creates VM without correct configuration.

**Cause:** Terraform generates instance template names with a timestamp suffix (e.g.
`digitaltwin-20260506075521314700000001`). A hardcoded template name `"digitaltwin"`
never matches.

**Fix:** Pass the template name as `INSTANCE_TEMPLATE` env var to the Cloud Function
from Terraform. The function reads it at runtime:
```python
os.environ.get('INSTANCE_TEMPLATE', 'digitaltwin')
```

---

## Pitfall 19: Persistent disk deleted when VM is deleted

**Symptom:** All database data lost after deleting and recreating the VM.

**Cause 1:** Instance template had `auto_delete` defaulting to `true` on the data disk
attachment. Fix: `auto_delete = false` in the instance template disk block.

**Cause 2 (more subtle):** The startup script detected the data disk by iterating
`/dev/sd*` and falling back to ephemeral storage when it couldn't find a disk >10 GB.
Device ordering is not guaranteed across reboots, so the wrong disk (or no disk) was
sometimes selected, causing PostgreSQL to reinitialise.

**Fix:** Use the stable GCP device name path:
```bash
DATA_DISK="/dev/disk/by-id/google-postgres-data"
```
GCP always exposes the disk at this path when `device_name = "postgres-data"` is set
in the instance template.

---

## Pitfall 20: Terraform rewrites Secret Manager values on every apply

**Symptom:** Correct API keys set manually in Secret Manager are overwritten with
`"placeholder-change-in-console"` on each `terraform apply`.

**Cause:** `google_secret_manager_secret_version` resources in `main.tf` were creating
new versions every apply. The latest version became the placeholder.

**Fix:** Remove all `google_secret_manager_secret_version` resources from Terraform.
Run `terraform state rm` for each before removing from config to prevent destruction.
Manage secret values entirely outside Terraform:
```bash
echo -n "VALUE" | gcloud secrets versions add SECRET_NAME \
  --data-file=- --project=digitaltwin-gcp-pr
```

---

## Pitfall 21: `docker exec` without `-i` does not forward stdin to container

**Symptom:** Python script piped via heredoc to `docker exec ... python3 -` runs but
does nothing — "Embedding 0 items" on a database with 5815 rows.

**Cause:** Without the `-i` flag, `docker exec` does not connect stdin to the
container process. `python3 -` reads empty stdin and exits immediately.

**Fix:** Always use `docker exec -i` when piping input:
```bash
docker exec -i digitaltwin python3 - <<PYEOF
...
PYEOF
```

---

## Pitfall 22: Embedding dimension mismatch — migration `e3f1c7fa505b` was empty

**Symptom:** `ValueError: expected 1024 dimensions, not 1536` when saving embeddings.

**Cause:** Migration `e3f1c7fa505b_update_embedding_dimension_to_1024.py` existed but
had an empty `upgrade()` body (`pass`). The database column remained `vector(1536)`
from the initial schema, while the SQLAlchemy model used `Vector(1024)` from
`EMBEDDING_DIM = 1024` in config.

**Fix:** The migration now alters the column:
```python
def upgrade():
    op.execute("ALTER TABLE dt_memory_items ALTER COLUMN embedding TYPE vector(1024)")
```
Embedding model: `voyage-3` (1024 dims). Do not use `voyage-large-2` (1536 dims).

---

## Pitfall 23: subject_id must match exactly between database and app config

**Symptom:** App responds "my memories are empty" despite 5815 memory items in
the database.

**Cause:** Memory items were exported from local development with
`subject_id = 'Василь Андрійович'` (Ukrainian Cyrillic). The GCP secret `subject-id`
was set to `'Vasil Andrijovich'` (Latin). The query filters by exact subject_id match.

**Fix:** Keep `subject-id` secret as `'Vasil Andrijovich'` (Latin, safe in config)
and update the database rows to match:
```sql
UPDATE dt_memory_items SET subject_id = 'Vasil Andrijovich';
```

---

## Pitfall 24: Exported memories have NULL embeddings — must re-embed after import

**Symptom:** App responds but all answers are generic — no memory context used.

**Cause:** The local database had never had embeddings generated (all NULL). The
pg_dump export correctly captured NULL values. The cloud database also has NULL
embeddings. Vector similarity search returns nothing.

**Fix:** After every data import, run the embedding script:
```bash
# On the VM, inside the container
docker exec -w /app digitaltwin python3 /app/embed.py
```
Uses `voyageai.AsyncClient` with `model="voyage-3"`, processes one item at a time
(batch of 50 causes Voyage to reject very long texts). Takes ~20-30 min for 5815 items.

---

## Secrets managed in GCP Secret Manager

| Secret name | Content |
|---|---|
| `anthropic-api-key` | Anthropic API key (`sk-ant-...`) |
| `voyage-api-key` | Voyage AI API key |
| `admin-api-key` | App admin key |
| `subject-id` | `Vasil Andrijovich` |
| `slack-bot-token` | Slack bot token (`xoxb-...`) |
| `slack-signing-secret` | Slack app signing secret |
| `slack-chat-channel-id` | Slack channel ID for `dt_chat` (without `slack:` prefix) |
| `slack-corrections-channel-id` | Slack channel ID for `dt_corrections` (without `slack:` prefix) |

---

## Operational runbook

### First-time deployment

1. Build and push amd64 image: `docker buildx build --platform linux/amd64 -t gcr.io/<project>/digitaltwin:latest --push .`
2. Create all secrets in Secret Manager (see table above)
3. `cd terraform && terraform apply -var-file=terraform.tfvars`
4. Copy webhook URL from `gcloud functions describe slack-webhook-proxy --format="value(httpsTrigger.url)"`
5. Set it in Slack app → Event Subscriptions → Request URL
6. Send a Slack message to trigger first VM creation
7. SSH into VM and run embedding script after VM startup completes

### After `terraform apply` (instance template changes)

The new template is used for all subsequent VM creations. No action needed for the
currently running VM.

### If database data is lost

1. From local machine: `docker exec postgres pg_dump --data-only --no-owner --table=dt_raw_sources --table=dt_memory_items -U digitaltwin -d digitaltwin > memory_export.sql`
2. `gcloud compute scp memory_export.sql digitaltwin-instance:/tmp/`
3. `gcloud compute ssh digitaltwin-instance -- "sudo docker cp /tmp/memory_export.sql postgres:/tmp/ && sudo docker exec postgres psql -U digitaltwin -d digitaltwin -f /tmp/memory_export.sql"`
4. Fix subject_id: `sudo docker exec postgres psql -U digitaltwin -d digitaltwin -c "UPDATE dt_memory_items SET subject_id = 'Vasil Andrijovich';"`
5. Run embedding script (see Pitfall 24)

### Debugging Cloud Functions

```bash
gcloud functions logs read slack-webhook-proxy --project=digitaltwin-gcp-pr --region=europe-central2 --limit=10
gcloud functions logs read slack-activity-handler --project=digitaltwin-gcp-pr --region=europe-central2 --limit=20
```

### Debugging VM startup

```bash
gcloud compute instances get-serial-port-output digitaltwin-instance \
  --project=digitaltwin-gcp-pr --zone=europe-central2-a 2>&1 | grep "startup-script:" | tail -30
```
