# Initial MVP Implementation Plan

## Goal

Deliver a working, containerized skeleton of the Digital Twin system that demonstrates
the core architecture without implementing every feature fully.

## MVP Scope

### In Scope

- FastAPI application with health endpoint
- PostgreSQL + pgvector schema (all 8 models)
- Alembic migration baseline
- LLM provider abstraction (Anthropic, OpenAI, Local stubs)
- Memory service: create candidate, approve, reject, retrieve
- Channel gateway: normalize, permission check, route
- Channel adapter stubs: Slack, Discord, WhatsApp
- Admin API: approve/reject candidate, list candidates, delete memory, export
- Audit logging on all memory operations
- Docker Compose: FastAPI + PostgreSQL + Redis
- Basic test suite: permission logic, candidate approval, namespace separation, audit logging
- .env.example with all required variables
- README with local run instructions
- Documentation: architecture, security, memory design, development process
- ADR series initialized

### Out of Scope for MVP

- Real Slack/Discord/WhatsApp webhook integration
- Background worker (Celery)
- Web UI
- OAuth2/JWT authentication
- Alembic auto-generated migration (manual schema creation via `CREATE TABLE`)
- MemPalace full integration (placeholder only)
- Embedding index tuning (HNSW/IVFFlat)
- Multi-subject support (single subject_id for MVP)

---

## Implementation Phases

### Phase 0 — Documentation and Planning (Complete)

- [x] docs/architecture.md
- [x] docs/security.md
- [x] docs/memory_design.md
- [x] docs/development_process.md
- [x] docs/development_log.md
- [x] docs/adr/001-database-choice.md
- [x] docs/adr/002-memory-separation.md
- [x] docs/adr/003-llm-abstraction.md
- [x] plans/initial_mvp_plan.md

### Phase 1 — Infrastructure

- [x] .env.example
- [x] requirements.txt
- [x] Dockerfile
- [x] docker-compose.yml
- [x] src/config.py
- [x] src/database.py

### Phase 2 — Data Models

- [x] src/models/base.py
- [x] src/models/raw_source.py
- [x] src/models/memory_item.py
- [x] src/models/entity.py
- [x] src/models/relationship.py
- [x] src/models/conversation_message.py
- [x] src/models/memory_candidate.py
- [x] src/models/audit_log.py
- [x] src/models/channel_config.py

### Phase 3 — LLM Abstraction

- [x] src/llm/base.py
- [x] src/llm/anthropic_provider.py
- [x] src/llm/openai_provider.py
- [x] src/llm/local_provider.py

### Phase 4 — Memory Service

- [x] src/memory/service.py

### Phase 5 — Channel Gateway

- [x] src/channels/gateway.py
- [x] src/channels/slack_adapter.py
- [x] src/channels/discord_adapter.py
- [x] src/channels/whatsapp_adapter.py

### Phase 6 — API Layer

- [x] src/api/health.py
- [x] src/api/memory.py
- [x] src/api/admin.py
- [x] src/main.py

### Phase 7 — Tests

- [x] tests/conftest.py
- [x] tests/test_channel_permissions.py
- [x] tests/test_memory_candidate.py
- [x] tests/test_memory_separation.py
- [x] tests/test_audit_logging.py

### Phase 8 — README

- [x] README.md

---

## Success Criteria

1. `docker compose up` starts all services without errors
2. `GET /health` returns `{"status": "ok"}`
3. All 5 test files pass with `pytest tests/`
4. No channel message can directly write a `MemoryItem` without admin approval
5. Every memory write generates a corresponding `AuditLog` entry
6. Digital Twin memory and Development memory have zero shared code paths in the test suite

---

## Risk Register

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| pgvector not installed in Postgres container | Low | Use `pgvector/pgvector:pg15` Docker image |
| asyncpg incompatibility with SQLAlchemy version | Medium | Pin versions in requirements.txt |
| Anthropic/OpenAI API key not available in CI | Low | Mock provider in tests |
| MemPalace not available | Low | Placeholder file-based dev memory until integration |
