# Digital Twin — Claude Code Instructions

## Session start

Run this at the start of every session to load prior development context:

```bash
.venv/bin/mempalace wake-up
```

This loads ~800 tokens of compressed project history (architecture decisions, working state, what's been built) without consuming the full context window.

## Development memory

Project decisions and session history are stored in MemPalace (local ChromaDB):

- Palace location: `~/.mempalace/palace`
- Wing: `digitaltwin`
- Rooms: `src`, `documentation`, `alembic`, `testing`, `plans`

After completing significant work, mine the updated files:

```bash
.venv/bin/mempalace mine /Users/macbook/Documents/GitHub/DigitalTwin
```

To search development memory:

```bash
.venv/bin/mempalace search "alembic async migration"
.venv/bin/mempalace search "candidate pipeline"
```

The MemPalace MCP server is configured in `.claude/settings.json` — tools
`mempalace_search`, `mempalace_add_drawer`, `mempalace_kg_add`, and
`mempalace_diary_write` are available during sessions when MCP is active.

## Architecture rules (must not be broken)

- All Digital Twin tables use `dt_` prefix
- No channel message can directly create a `MemoryItem` — always via `MemoryCandidate → approval`
- `AuditLog` has no update/delete ORM methods
- `MemoryService.llm` is optional — candidate creation never needs LLM

## Running the stack

```bash
# Start Postgres
docker compose up -d postgres

# Run API (from project root)
.venv/bin/uvicorn src.main:app --reload

# Run tests (no Docker required)
.venv/bin/pytest tests/ -v
```

## Environment

- Python 3.13 only — asyncpg has no wheel for 3.14
- `DATABASE_URL` in `.env` must use `@localhost` (not `@postgres`) for local tools
- `env_ignore_empty=True` in pydantic-settings prevents the empty `ANTHROPIC_API_KEY=''`
  injected by the IDE from overriding the real key in `.env`
