# Digital Twin System — Architecture

## Overview

The Digital Twin system creates a memory-grounded conversational agent that represents a specific
person. It ingests documents, articles, transcripts, and approved conversations, extracts
structured memories, and enables interaction through messaging channels (Slack, Discord,
WhatsApp) and eventually a web UI.

---

## System Components

### 1. Ingestion Pipeline

- Accepts raw sources: documents, articles, transcripts, conversations
- Stores originals as `RawSource` records with full provenance metadata
- Queues extraction jobs via background worker (Celery + Redis or async task queue)
- Produces `MemoryCandidate` records that enter a human-review queue
- No candidate is ever promoted to long-term memory without explicit admin approval

### 2. Memory System — Two Strictly Separated Namespaces

See `docs/memory_design.md` for full detail.

| Namespace | Purpose | Mutated by |
|-----------|---------|-----------|
| **Digital Twin Memory** | Biographical, personality, ideas, events, preferences, conversation history of the represented person | Admin-approved candidates only |
| **Development Memory** | Project history, architecture decisions, bugs, prompts, Claude Code sessions | MemPalace / dev tooling only |

These two namespaces must never share a database table, a retrieval code path, or a prompt context.

### 3. FastAPI Backend

- Async REST API: health, memory management, admin operations, channel ingest endpoints
- Async SQLAlchemy sessions with PostgreSQL + pgvector
- Authentication: Admin API key header (MVP) → OAuth2/JWT (future)
- All routes are versioned under `/api/v1/`

### 4. Channel Gateway

- Normalizes inbound messages from Slack, Discord, WhatsApp into a `NormalizedMessage` object
- Enforces per-channel permission policy via `ChannelConfig` database records
- Routes messages to one of three paths:
  - `read_only_chat` → Chat handler (no memory write possible)
  - `learn_candidate` → Extraction pipeline → `MemoryCandidate` (pending review)
  - `admin` → Memory Admin API → Approval queue

### 5. LLM Provider Abstraction

- `BaseLLMProvider` interface: `complete()`, `embed()`
- Concrete backends: Anthropic Claude, OpenAI GPT, Ollama/vLLM (local)
- Provider selected via `LLM_PROVIDER` environment variable
- No provider-specific code outside `src/llm/`
- Prompt templates enforce content delimiters to prevent injection

### 6. Admin Review Queue

- All memory candidates require explicit approval before promotion to long-term memory
- `AuditLog` records every read, write, delete, approval, and rejection
- Deletion soft-deletes (status = `deleted`) to preserve audit trail; embedding vector zeroed

---

## Data Flow

```
External Channel Message
        │
        ▼
Channel Adapter (Slack / Discord / WhatsApp)
        │  normalize to NormalizedMessage
        ▼
Channel Gateway
        │  check ChannelConfig permission
        ├─── read_only_chat ──► Chat Handler ──► LLM ──► Response
        │
        ├─── learn_candidate ─► Extraction Pipeline
        │                              │
        │                              ▼
        │                      MemoryCandidate (pending)
        │                              │
        │                      Admin Review API
        │                              │
        │               approve ───────┴─────── reject
        │                  │
        │                  ▼
        │           MemoryItem (active)
        │
        └─── admin ───────► Memory Admin API
```

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| Web Framework | FastAPI 0.110+ |
| Database | PostgreSQL 15 + pgvector extension |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Cache / Queue | Redis 7 |
| Containerization | Docker + Docker Compose v2 |
| LLM (cloud) | Anthropic Claude / OpenAI GPT |
| LLM (local) | Ollama / vLLM |
| Testing | pytest + pytest-asyncio |
| Dev Memory | MemPalace (or placeholder integration) |

---

## Directory Structure

```
DigitalTwin/
├── docs/               ← Architecture, security, memory design docs
│   └── adr/            ← Architecture Decision Records
├── plans/              ← Implementation plans
├── src/
│   ├── api/            ← FastAPI route handlers
│   ├── channels/       ← Channel adapters and gateway
│   ├── llm/            ← LLM provider abstraction
│   ├── memory/         ← Memory service
│   ├── models/         ← SQLAlchemy ORM models
│   ├── config.py       ← Settings (pydantic-settings)
│   ├── database.py     ← Async engine and session factory
│   └── main.py         ← FastAPI app factory
├── tests/              ← pytest test suite
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── requirements.txt
└── README.md
```
