# Digital Twin

A local/VM-deployable system that creates a memory-grounded conversational agent
representing a person. It ingests documents, articles, and transcripts; extracts
structured memories via LLM; and stores them in a human-reviewed memory bank.

**Memory security guarantee:** No message or document can directly write long-term
memory. All content flows through a candidate pipeline requiring explicit admin approval.

---

## Current Status (2026-05-07)

The following is working end-to-end:

- **Local Development**: PostgreSQL + pgvector running via Docker, FastAPI with hot reload
- **Document Ingest**: raw text, `.pdf`, `.docx`, `.txt` files with automatic chunking
- **Memory Pipeline**: Two extraction modes (`biographical` and `authored_work`) with admin approval
- **Chat System**: Questions answered in subject's voice, grounded in stored memories
- **Correction Loop**: Subject corrections auto-approved and immediately improve responses
- **Slack Integration**: Three channels — chat, corrections, and story submission (text + voice)
- **Voice Pipeline**: Slack voice messages → GCS storage → Google Speech-to-Text → knowledge base
- **GCP Production**: Full end-to-end Slack → Cloud Function → VM → response flow working in production

**GCP Infrastructure (Production — fully working):**
- **Auto-Scaling VMs**: Slack message → Cloud Function → VM wakes up (or creates from template) → app starts → response in Slack thread
- **VM Auto-Shutdown**: Cloud Scheduler runs every 5 min; stops VMs idle longer than 5 min via `last-activity` instance metadata
- **VM Wake-Up**: Stopped VM is resumed with `compute.instances.start` (not recreated); existing Docker containers are started, not re-created
- **Persistent Storage**: PostgreSQL data survives VM stop/start via persistent disk (`prevent_destroy = true`, `auto_delete = false`)
- **Secret Management**: All secrets in GCP Secret Manager; fetched via metadata API (no gcloud on COS)
- **Channel Auto-Registration**: All three Slack channels registered automatically on every VM boot
- **Memory Embeddings**: 5815 memories embedded with `voyage-3` (1024 dims), stored in pgvector
- **GCS Audio Storage**: Voice messages stored at `gs://{bucket}/voice/` with 90-day auto-delete lifecycle

**Not yet implemented:**
- Discord/WhatsApp adapters (stubs only)
- Web UI
- Multi-subject support

---

## Quick Start

### Prerequisites

- Docker Desktop (or OrbStack)
- Python 3.13 (`/usr/local/bin/python3.13`)

### 1. Clone and configure

```bash
git clone <repo-url>
cd DigitalTwin
cp .env.example .env
# Edit .env:
#   ANTHROPIC_API_KEY=sk-ant-...
#   ADMIN_API_KEY=something-secret
#   SUBJECT_ID=alice   (or whoever the twin represents)
```

### 2. Start Postgres

```bash
docker compose up -d postgres
```

### 3. Create the venv and install dependencies

```bash
/usr/local/bin/python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 4. Run database migrations

```bash
.venv/bin/alembic upgrade head
```

You should see:
```
Running upgrade  -> 0001, enable pgvector extension
Running upgrade 0001 -> 6e73234c7695, initial schema
Running upgrade 6e73234c7695 -> 0003, add authored_work memory types
Running upgrade 0003 -> 0004, add chat sessions table
Running upgrade 0004 -> 0005, add submit_content permission
```

### 5. Seed the first channel config

```bash
.venv/bin/python - <<'EOF'
import asyncio
from src.database import AsyncSessionLocal
from src.models.channel_config import ChannelConfig, ChannelType, PermissionLevel

async def seed():
    async with AsyncSessionLocal() as session:
        session.add(ChannelConfig(
            channel_id="api:local",
            channel_type=ChannelType.api,
            permission_level=PermissionLevel.learn_candidate,
            is_active=True,
        ))
        await session.commit()
        print("Done.")

asyncio.run(seed())
EOF
```

### 6. Start the API

```bash
.venv/bin/uvicorn src.main:app --reload
```

### 7. Verify

```bash
curl http://localhost:8000/health
curl http://localhost:8000/health/db
```

---

## Ingesting Documents

### Extraction modes

Choose the right mode for your document:

| Mode | Use when | Extracts |
|------|----------|----------|
| `biographical` (default) | Document is *about* the person — biography, article, interview transcript | `biographical`, `personality`, `idea`, `event`, `preference`, `skill`, `relationship` |
| `authored_work` | Document is *written by* the person — book, essay, blog post | `belief`, `concept`, `voice`, `value`, `idea`, `personality` |

### Upload a file (.pdf, .docx, .txt)

```bash
# Biographical mode (default) — document about the person
curl -s -X POST http://localhost:8000/api/v1/admin/sources/upload \
  -H "X-Admin-Key: your-admin-key" \
  -F "file=@/path/to/biography.pdf" \
  -F "source_type=document" \
  -F "subject_hint=Person's name and brief background" \
  -F "title=Optional title" | python3 -m json.tool

# Authored-work mode — document written by the person (book, essay, blog)
curl -s -X POST http://localhost:8000/api/v1/admin/sources/upload \
  -H "X-Admin-Key: your-admin-key" \
  -F "file=@/path/to/their-book.docx" \
  -F "source_type=document" \
  -F "extraction_mode=authored_work" \
  -F "subject_hint=Person's name — author of this document" \
  -F "title=Book title" | python3 -m json.tool
```

Large files (books, long articles) are automatically split into 8 KB chunks and processed
in sequence. A 335 KB book produces ~42 chunks. The request blocks until all chunks finish.

### Submit raw text

```bash
curl -s -X POST http://localhost:8000/api/v1/admin/sources \
  -H "X-Admin-Key: your-admin-key" \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "article",
    "extraction_mode": "authored_work",
    "title": "Title",
    "subject_hint": "Person name and background",
    "content": "Full text here..."
  }' | python3 -m json.tool
```

Both return a list of `candidate_ids` — extracted memory candidates pending review.

---

## Reviewing and Approving Candidates

```bash
# List pending candidates
curl -s http://localhost:8000/api/v1/admin/candidates \
  -H "X-Admin-Key: your-admin-key" | python3 -m json.tool

# Approve one
curl -s -X POST http://localhost:8000/api/v1/admin/candidates/<id>/approve \
  -H "X-Admin-Key: your-admin-key" \
  -H "Content-Type: application/json" \
  -d '{"reviewer_id": "you"}' | python3 -m json.tool

# Reject one
curl -s -X POST http://localhost:8000/api/v1/admin/candidates/<id>/reject \
  -H "X-Admin-Key: your-admin-key" \
  -H "Content-Type: application/json" \
  -d '{"reviewer_id": "you", "reason": "Not accurate"}' | python3 -m json.tool

# Approve all pending at once (bash loop)
for id in <id1> <id2> <id3>; do
  curl -s -X POST http://localhost:8000/api/v1/admin/candidates/$id/approve \
    -H "X-Admin-Key: your-admin-key" \
    -H "Content-Type: application/json" \
    -d '{"reviewer_id": "you"}' > /dev/null && echo "Approved $id"
done
```

---

## API Reference

All admin endpoints require `X-Admin-Key` header.

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check |
| `GET` | `/health/db` | Database connectivity |

### Channel Ingest (requires configured channel)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/memory/ingest` | Submit a channel message |

### Admin — Document Ingest

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/admin/sources` | Ingest raw text → extract candidates |
| `POST` | `/api/v1/admin/sources/upload` | Upload .pdf / .docx / .txt → extract candidates |

### Admin — Candidate Review

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/admin/candidates` | List candidates (`?status_filter=pending`) |
| `POST` | `/api/v1/admin/candidates/{id}/approve` | Approve → creates MemoryItem |
| `POST` | `/api/v1/admin/candidates/{id}/reject` | Reject with optional reason |

### Admin — Memory Management

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/admin/memory` | List active memory items |
| `DELETE` | `/api/v1/admin/memory/{id}` | Soft-delete (status=deleted, embedding zeroed) |
| `GET` | `/api/v1/admin/export` | GDPR export — all memory items as JSON |

### Admin — Chat

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/admin/chat` | Ask a question; receive answer in subject's voice |
| `POST` | `/api/v1/admin/chat/{session_id}/correct` | Submit a correction to a previous response |

Chat request body: `{"message": "...", "memory_limit": 30, "channel_id": "api:local"}`
Chat response includes `session_id` — pass it to the correction endpoint.

Correction request body: `{"correction": "...", "reviewer_id": "subject"}`
Corrections are auto-approved at `confidence=1.0` and immediately enter the knowledge base.

### Slack Events

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/slack/events` | Slack Events API webhook (handles URL verification + messages) |

Interactive docs: `http://localhost:8000/docs` (development mode only)

---

## Memory Types

The LLM assigns one of these types to each extracted candidate automatically.

### Biographical mode (documents *about* the person)

| Type | What it captures |
|------|-----------------|
| `biographical` | Fixed life facts — birthplace, education, moves |
| `personality` | Character traits, communication style |
| `idea` | Opinions, beliefs, intellectual positions |
| `event` | Things that happened — conferences, achievements, trips |
| `preference` | Likes, dislikes, habits |
| `skill` | Capabilities and expertise |
| `relationship` | Connections to people, places, organisations |
| `conversation` | Distilled insights from conversations |

### Authored-work mode (documents *written by* the person)

| Type | What it captures |
|------|-----------------|
| `belief` | Deep philosophical or spiritual conviction, even when implicit |
| `concept` | Personal term, symbol, or framework used in a distinctive way — always explains the author's specific meaning, not the generic definition |
| `voice` | Characteristic rhetorical or stylistic pattern — includes a quoted phrase from the source as evidence |
| `value` | Core principle revealed as deeply important through the writing |

---

## Chatting with the Digital Twin

```bash
# Ask a question
curl -s -X POST http://localhost:8000/api/v1/admin/chat \
  -H "X-Admin-Key: your-admin-key" \
  -H "Content-Type: application/json" \
  -d '{"message": "Що ти думаєш про свободу і духовність?"}' | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('session_id:', d['session_id'])
print()
print(d['response'])
"

# Subject corrects a response (auto-approved, confidence=1.0)
curl -s -X POST http://localhost:8000/api/v1/admin/chat/<SESSION_ID>/correct \
  -H "X-Admin-Key: your-admin-key" \
  -H "Content-Type: application/json" \
  -d '{"correction": "Насправді я думаю...", "reviewer_id": "vasil"}' | python3 -m json.tool
```

Set `SUBJECT_NAME=Vasil Andrijovich` (or the subject's real name) in `.env` so the system prompt uses the correct identity.

---

## Slack Integration

The Digital Twin can participate in Slack channels with different permission levels.

### Channel layout

| Slack channel     | Permission        | Who                     | Behaviour                                                                                                      |
|-------------------|-------------------|-------------------------|----------------------------------------------------------------------------------------------------------------|
| `#dt-chat`        | `read_only_chat`  | Everyone                | Messages get a threaded chat response                                                                          |
| `#dt-corrections` | `learn_candidate` | Father only (allowlist) | **Top-level** message → chat response (not stored); **Thread reply** → stored as `Q: …\nCorrection: …` linked to the question. Supports voice. |
| `#dt-stories`     | `submit_content`  | Father only (allowlist) | Text or voice messages → GCS → Speech-to-Text → pending candidates for admin review                           |

**Why thread-based corrections?** Asking a question (top-level) shows the current answer without storing it. The father replies in that thread to correct the answer — the correction is stored with the original question embedded, so vector search retrieves it precisely when the same question is asked again.

### One-time setup

**1. Create a Slack app**

Go to https://api.slack.com/apps → Create New App → From scratch.

**OAuth & Permissions** → Bot Token Scopes:
- `chat:write`
- `channels:history`
- `groups:history`
- `files:read`

Install to workspace, copy the **Bot Token** (`xoxb-...`).
**Basic Information** → copy the **Signing Secret**.

**2. Add to `.env`**

```
SLACK_BOT_TOKEN=xoxb-your-token
SLACK_SIGNING_SECRET=your-signing-secret
SUBJECT_NAME=Vasil Andrijovich
```

**3. Expose your server**

```bash
ngrok http 8000
```

**4. Enable Events API**

Slack app → **Event Subscriptions** → Enable → Request URL:
```
https://<your-ngrok-url>/api/v1/slack/events
```
Subscribe to bot events: `message.channels`, `message.groups`.

**5. Create channels and invite the bot**

Create `#dt-chat`, `#dt-corrections`, and `#dt-stories` in Slack. In each: `/invite @YourBotName`.

**6. Seed channel configs**

Get channel IDs (right-click channel → View channel details) and father's user ID (his profile → ⋮ → Copy member ID):

```bash
.venv/bin/python - <<'EOF'
import asyncio
from src.database import AsyncSessionLocal
from src.models.channel_config import ChannelConfig, ChannelType, PermissionLevel

async def seed():
    async with AsyncSessionLocal() as session:
        session.add(ChannelConfig(
            channel_id="slack:C_CHAT_CHANNEL_ID",
            channel_type=ChannelType.slack,
            permission_level=PermissionLevel.read_only_chat,
            is_active=True,
        ))
        session.add(ChannelConfig(
            channel_id="slack:C_CORRECTIONS_CHANNEL_ID",
            channel_type=ChannelType.slack,
            permission_level=PermissionLevel.learn_candidate,
            is_active=True,
            allowed_user_ids=["U_FATHER_SLACK_USER_ID"],
        ))
        session.add(ChannelConfig(
            channel_id="slack:C_STORIES_CHANNEL_ID",
            channel_type=ChannelType.slack,
            permission_level=PermissionLevel.submit_content,
            is_active=True,
            allowed_user_ids=["U_FATHER_SLACK_USER_ID"],
        ))
        await session.commit()
        print("Done.")

asyncio.run(seed())
EOF
```

In GCP production, channels are registered automatically on VM boot via the startup script — no manual seeding needed.

---

## GCP Auto-Scaling Deployment

The Digital Twin can be deployed to Google Cloud Platform with automatic scaling based on Slack activity. This provides a cost-effective production setup where VMs only run when needed.

### Architecture Overview

- **Cloud Functions**: Handle Slack webhooks and VM lifecycle management
- **VM Instances**: Auto-created from templates when activity is detected
- **Container Registry**: Stores the latest Digital Twin container image
- **Persistent Disks**: PostgreSQL data survives VM restarts
- **Pub/Sub**: Event-driven communication between components

### Cost Optimization

- **Pay-per-use**: VMs only run during active periods (typically <$1/day)
- **Automatic shutdown**: VMs terminate after 30 minutes of inactivity
- **Persistent storage**: Database survives VM lifecycle

### Prerequisites

- Google Cloud Project with billing enabled
- `gcloud` CLI installed and authenticated
- Terraform installed
- Container Registry API enabled
- Cloud Functions API enabled
- Compute Engine API enabled

### Deployment Steps

**1. Configure Terraform**

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your project settings
```

**2. Set up secrets in GCP Console**

Before deploying, create the application secrets in Google Secret Manager:

```bash
gcloud secrets create anthropic-api-key --data-file=- <<< "your-anthropic-api-key"
gcloud secrets create admin-api-key --data-file=- <<< "your-secure-admin-key"
gcloud secrets create voyage-api-key --data-file=- <<< "your-voyage-api-key"
gcloud secrets create subject-id --data-file=- <<< "default"
gcloud secrets create slack-bot-token --data-file=- <<< "xoxb-..."
gcloud secrets create slack-signing-secret --data-file=- <<< "..."

# Channel IDs (from Slack channel details)
gcloud secrets create slack-chat-channel-id --data-file=- <<< "C_CHAT_CHANNEL_ID"
gcloud secrets create slack-corrections-channel-id --data-file=- <<< "C_CORRECTIONS_CHANNEL_ID"
gcloud secrets create slack-stories-channel-id --data-file=- <<< "C_STORIES_CHANNEL_ID"

# Father's Slack user ID (his profile → ⋮ → Copy member ID)
gcloud secrets create slack-father-user-id --data-file=- <<< "U_FATHER_USER_ID"
```

**3. Build and push container**

```bash
# Build the container
docker build -t gcr.io/YOUR_PROJECT/digitaltwin:latest .

# Push to GCR
gcloud auth configure-docker
docker push gcr.io/YOUR_PROJECT/digitaltwin:latest
```

**4. Deploy infrastructure**

```bash
# Initialize and plan
terraform init
terraform plan

# Deploy
terraform apply
```

**5. Configure Slack webhook**

Update your Slack app's Event Subscription URL to point to the deployed Cloud Function:
```
https://YOUR_REGION-YOUR_PROJECT.cloudfunctions.net/webhook_proxy
```

### VM Lifecycle

- **Trigger**: Slack message → `slack-webhooks` Pub/Sub → `slack-activity-handler` Cloud Function
- **Wake-up**: If VM is stopped (`TERMINATED`), resumes it via `compute.instances.start`; if absent, creates from instance template
- **Container start**: Startup script detects existing containers and runs `docker start` instead of `docker run` on wake-up
- **Health check**: Cloud Function polls `GET /health` every 10 s (480 s timeout) before forwarding the Slack event
- **Activity tracking**: Every successful Slack event stamps `last-activity` into VM instance metadata
- **Auto-shutdown**: `cleanup-inactive-vms` Cloud Scheduler job runs every 5 min; stops VMs idle > 5 min
- **Persistent data**: PostgreSQL disk survives stop/start — no data loss on shutdown

### Monitoring

- **Cloud Logging**: All application logs available in GCP console
- **VM Metrics**: CPU, memory, disk usage monitoring
- **Function Logs**: Webhook and lifecycle event logs
- **Cost Tracking**: GCP billing dashboard for usage analysis

### Scaling Behavior

| Activity Level | VM State | Cost Impact |
|----------------|----------|-------------|
| No messages    | Stopped  | $0          |
| Occasional     | Auto-start/stop | <$1/day     |
| Frequent       | Mostly running | ~$20-30/day |

### Troubleshooting GCP

**VM won't start / Cloud Function errors:**
```bash
gcloud functions logs read slack-activity-handler \
  --project=digitaltwin-gcp-pr --region=europe-central2 --limit=20
```

**Startup script failing:**
```bash
gcloud compute instances get-serial-port-output digitaltwin-instance \
  --project=digitaltwin-gcp-pr --zone=europe-central2-a 2>&1 | grep "startup-script:" | tail -30
```

**App not responding on port 8000 despite VM running:**
COS iptables blocks all external traffic by default. The startup script adds a rule —
if missing, add it manually:
```bash
gcloud compute ssh digitaltwin-instance ... -- "sudo iptables -A INPUT -p tcp --dport 8000 -j ACCEPT"
```

**Slack webhook returns 401:**
The webhook proxy caches the signing secret at cold start. Force a redeploy to reload
the correct secret from Secret Manager:
```bash
cd terraform && terraform apply -var-file=terraform.tfvars
```

**App says "memories are empty":**
Either embeddings are NULL (run embed.py script) or `subject_id` doesn't match.
Check: `sudo docker exec postgres psql -U digitaltwin -d digitaltwin -c 'SELECT DISTINCT subject_id FROM dt_memory_items;'`

See `docs/cloud_deployment_pitfalls.md` for the complete list of all 24 pitfalls and their solutions.

---

## Channel Permission Levels

| Level              | Can chat | Can create candidates       | Auto-approved | Can approve |
|--------------------|----------|-----------------------------|---------------|-------------|
| `read_only_chat`   | Yes      | No                          | —             | No          |
| `learn_candidate`  | Yes      | Yes (high-confidence)       | Yes           | No          |
| `submit_content`   | No       | Yes (pending admin review)  | No            | No          |
| `admin`            | Yes      | Yes                         | Yes           | Yes         |

Unknown or inactive channels receive `403 Forbidden`.

---

## Development Memory (MemPalace)

The project uses [MemPalace](https://github.com/MemPalace/mempalace) as a local-first
development memory layer. It stores the codebase verbatim in a local ChromaDB vector
store so Claude can search prior decisions and context without loading the full codebase
into the context window every session.

This is entirely separate from the Digital Twin's personal memory (which lives in
PostgreSQL). MemPalace only tracks development artifacts — source files, docs, ADRs.

### First-time setup

MemPalace is already in `requirements.txt`. After installing dependencies:

```bash
# Initialise the palace (detects rooms from folder structure)
.venv/bin/mempalace init /path/to/DigitalTwin

# Mine all project files into the palace (272 drawers across 7 rooms)
.venv/bin/mempalace mine /path/to/DigitalTwin
```

The palace is stored at `~/.mempalace/palace` — outside the repo, never committed.

### Session workflow

**Start of every session** — load compressed project context (~800 tokens):

```bash
.venv/bin/mempalace wake-up
```

This prints a compressed summary of the codebase and prior context. Feed it to Claude
at the start of a session to restore working knowledge without re-reading every file.

**After making significant changes** — re-index updated files:

```bash
.venv/bin/mempalace mine /path/to/DigitalTwin
```

Idempotent — only processes files that changed since the last mine.

**Search development memory:**

```bash
.venv/bin/mempalace search "alembic async migration"
.venv/bin/mempalace search "candidate pipeline"
.venv/bin/mempalace search "env_ignore_empty"
```

**Check what's indexed:**

```bash
.venv/bin/mempalace status
```

### MCP integration (Claude Code)

The MCP server is pre-configured in `.claude/settings.json`. When you open this project
in Claude Code, the `mempalace-mcp` server starts automatically and exposes these tools
to Claude:

| Tool                    | What it does                                                    |
|-------------------------|-----------------------------------------------------------------|
| `mempalace_search`      | Semantic search across all indexed drawers                      |
| `mempalace_add_drawer`  | File a verbatim chunk into a room                               |
| `mempalace_kg_add`      | Store a typed architectural fact (subject → predicate → object) |
| `mempalace_diary_write` | Record an agent observation for later recall                    |

No setup needed beyond installing dependencies and running `mempalace init` once.

---

## Running Tests

```bash
# Unit tests — no Docker required
.venv/bin/pytest tests/ -v

# All tests
docker compose up -d postgres
.venv/bin/pytest tests/ -v
```

---

## Project Structure

```
src/
  api/          ← FastAPI routes (health, memory ingest, admin, slack events)
  channels/     ← Channel adapters (Slack, Discord, WhatsApp stubs) + gateway
  ingest/       ← Document parser (.pdf/.docx/.txt) + LLM extractor + transcriber
  llm/          ← LLM provider abstraction (Anthropic, OpenAI, Local)
  memory/       ← Memory service (candidate pipeline + retrieval)
  models/       ← SQLAlchemy ORM models (all dt_ prefixed)
  storage/      ← GCS audio upload (voice messages)
  config.py     ← Settings via pydantic-settings
  database.py   ← Async SQLAlchemy engine and session
  main.py       ← FastAPI app factory
alembic/
  versions/     ← Migration files (0001–0005)
docs/
  adr/          ← Architecture Decision Records
plans/
tests/
```

---

## Troubleshooting

### Slack: `ssl.SSLCertVerificationError` on outbound messages

macOS Python 3.13 does not use the system certificate store for urllib-based clients.
`slack_sdk.WebClient` uses urllib internally, so it fails to verify Slack's certificate.

**Fix** (already applied in `src/channels/slack_adapter.py`): pass a `certifi`-based SSL context:

```python
import ssl, certifi
ssl_context = ssl.create_default_context(cafile=certifi.where())
client = WebClient(token=token, ssl=ssl_context)
```

If you see this error after a fresh install, make sure `certifi` is installed:
```bash
.venv/bin/pip install certifi
```

### Slack: URL verification fails ("Your URL didn't respond")

Two common causes:
1. `request.body()` was already consumed before `request.json()` — fixed by parsing the body bytes directly with `json.loads(body)`.
2. uvicorn is not running or ngrok URL has changed — restart ngrok and update the Events API URL in the Slack app settings.

### Chat returns empty response / Internal Server Error

Run `alembic upgrade head` — a migration may not have been applied.

---

## Security Notes

- Never commit `.env` (listed in `.gitignore`)
- Change `ADMIN_API_KEY` before any real deployment
- All channel messages are untrusted input — never interpolated into prompts directly
- Retrieved memories are wrapped in delimited context blocks before LLM calls
- See `docs/security.md` for the full threat model

---

## Development Memory

Project decisions and session history live in:
- `docs/development_log.md` — running session log
- `docs/adr/` — Architecture Decision Records

This is entirely separate from Digital Twin personal memory. See `docs/memory_design.md`.
