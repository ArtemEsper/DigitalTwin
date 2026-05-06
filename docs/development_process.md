# Digital Twin System — Development Process

## Principles

1. **Separation of concerns**: Digital Twin memory and Development memory are never mixed.
2. **Explicit over implicit**: Policy checks are deterministic code, not hidden agent behavior.
3. **Security by default**: All external input is untrusted until proven otherwise.
4. **Modular deployment**: Every component must be independently deployable on a VM or local machine.
5. **Auditability**: Every memory operation is logged before it is returned to the caller.

---

## Repository Conventions

### Branch Strategy

```
main          — stable, deployable
dev           — integration branch
feature/*     — feature branches, PR into dev
fix/*         — bug fix branches, PR into dev
```

### Commit Message Format

```
<type>(<scope>): <short description>

<body — what and why>

<footer — references>
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `security`

Examples:
- `feat(memory): add candidate approval endpoint`
- `security(channels): enforce allowlist check before message processing`
- `docs(adr): add ADR-004 for Redis queue choice`

### Architecture Decision Records

Every non-trivial architectural decision gets an ADR in `docs/adr/`:

```
docs/adr/NNN-short-title.md
```

Template: see any existing ADR. Required sections: Status, Context, Decision, Consequences.

---

## Development Setup

### Prerequisites

- Docker Desktop (or OrbStack)
- Python 3.11+
- `uv` or `pip` for package management
- `make` (optional but recommended)

### First-Time Setup

```bash
cp .env.example .env
# Edit .env with real API keys (never commit this file)

docker compose up -d postgres redis
pip install -r requirements.txt
alembic upgrade head
uvicorn src.main:app --reload
```

### Running Tests

```bash
# Unit tests only (no database required)
pytest tests/ -m unit

# Integration tests (requires docker services)
docker compose up -d postgres redis
pytest tests/ -m integration

# All tests
pytest tests/
```

---

## Development Memory Workflow

All notable development events should be recorded in `docs/development_log.md`:

| Event Type | What to record |
|-----------|---------------|
| Session start | Goals for the session |
| Architecture decision | ADR created + link |
| Bug found | Description, root cause, fix |
| Prompt experiment | Prompt used, result, conclusion |
| Dependency added | Package, version, why |
| Security concern | Issue, mitigation applied |

When MemPalace integration is available, these log entries will also be pushed to the dev
memory namespace for cross-session recall.

---

## Code Quality

- All new Python modules must have corresponding tests in `tests/`
- Type annotations required on all public function signatures
- No `print()` in production code — use `logging` module
- No hardcoded credentials, endpoints, or model names outside `src/config.py`
- `mypy` for type checking (configured in `pyproject.toml` when added)

---

## Deployment Checklist

Before any deployment:

- [ ] `.env` file present and not committed
- [ ] All tests passing
- [ ] `alembic upgrade head` applied to target database
- [ ] `ADMIN_API_KEY` changed from default
- [ ] Channel configs created in database for all active channels
- [ ] pgvector extension installed on PostgreSQL instance
- [ ] Redis reachable from FastAPI container
- [ ] Audit log table verified writable
