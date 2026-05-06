# ADR-001: PostgreSQL + pgvector for Memory Storage

**Status:** Accepted
**Date:** 2026-04-27

## Context

The system needs to store structured memory items with semantic embeddings for similarity
search, relational data (entities, relationships, audit logs), and JSON metadata. Options
considered:

- PostgreSQL + pgvector
- Weaviate (dedicated vector DB)
- Chroma (embedded vector DB)
- Qdrant (dedicated vector DB)
- SQLite + FAISS (local only)

## Decision

Use **PostgreSQL 15 + pgvector extension** for all Digital Twin memory storage in the MVP.

## Rationale

1. **Single system**: Relational data (audit logs, channel configs, candidates) and vector
   data (memory embeddings) in one database reduces operational complexity.
2. **ACID guarantees**: Memory writes and audit log entries need transactional consistency.
3. **pgvector maturity**: Production-ready, supports cosine similarity, IVFFlat and HNSW indexes.
4. **Familiar tooling**: SQLAlchemy 2.0 has native pgvector support via `pgvector-python`.
5. **Docker-deployable**: Official PostgreSQL Docker image with pgvector available.

## Consequences

- All developers need pgvector installed locally (provided via Docker Compose).
- Embedding dimension must be fixed at schema creation time (1536 for OpenAI, 1024 for
  Anthropic, configurable via `EMBEDDING_DIM` env var).
- For very large memory stores (>10M items), a dedicated vector DB migration path should
  be revisited (ADR to be written).
