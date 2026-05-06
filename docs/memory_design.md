# Digital Twin System — Memory Design

## Two-Namespace Principle

The system maintains **two completely separate memory namespaces** that must never be mixed:

| Namespace | Database Schema | Purpose |
|-----------|----------------|---------|
| **Digital Twin Memory** | `dt_*` table prefix | Biographical facts, personality, ideas, events, preferences, conversation history of the represented person |
| **Development Memory** | External (MemPalace / dev tooling) | Project history, architecture decisions, bugs, prompts, Claude Code sessions |

**Enforcement rules:**
- No shared SQLAlchemy models or tables between namespaces
- No shared retrieval code paths
- No shared LLM prompt context
- Development memory tooling must never receive Digital Twin memory content and vice versa

---

## Digital Twin Memory

### Memory Types

| Type | Description | Example |
|------|-------------|---------|
| `biographical` | Facts about the person's life | "Born in 1985 in Chicago" |
| `personality` | Character traits, tendencies, communication style | "Tends to use Socratic questioning" |
| `idea` | Ideas, opinions, intellectual positions | "Believes distributed systems are overhyped" |
| `event` | Significant events or experiences | "Attended NeurIPS 2023, was impressed by X" |
| `preference` | Likes, dislikes, aesthetics | "Prefers async communication over meetings" |
| `skill` | Capabilities and expertise | "Expert in Rust, intermediate in Go" |
| `relationship` | Connections to people/organizations | "Close collaborator with Alice at Org X" |
| `conversation` | Distilled memory from approved conversations | "Discussed AI safety with Bob, concluded Y" |

### Memory Item Schema

Every `MemoryItem` record includes:

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `subject_id` | String | Identifier for the represented person |
| `memory_type` | Enum | One of the types above |
| `content` | Text | Human-readable memory statement |
| `embedding` | Vector(1536) | Semantic embedding for similarity search |
| `source_ids` | UUID[] | References to originating `RawSource` records |
| `confidence` | Float [0,1] | Confidence score from extraction |
| `tags` | String[] | Free-form tags for filtering |
| `status` | Enum | `active` \| `deleted` \| `exported` |
| `created_at` | Timestamp | Immutable creation time |
| `updated_at` | Timestamp | Last update time |

### Candidate Pipeline

All new memories enter as `MemoryCandidate` records first:

```
RawSource ingest
    │
    ▼
Extraction (LLM extracts candidate memories from source)
    │
    ▼
MemoryCandidate (status = pending)
    │
    ├── Admin approves ──► MemoryItem (status = active) + AuditLog
    └── Admin rejects ──► MemoryCandidate (status = rejected) + AuditLog
```

**No automatic promotion is permitted.**

### Vector Search

- Embeddings generated via `BaseLLMProvider.embed()` at candidate approval time
- pgvector cosine similarity search: `ORDER BY embedding <=> query_embedding LIMIT k`
- Minimum confidence threshold configurable (default: 0.6)
- Deleted items (status = `deleted`) excluded from all search results

### Source Attribution

Every `MemoryItem` links back to one or more `RawSource` records via `source_ids`. The
`RawSource` record preserves:
- Original content (verbatim)
- Source type (article / document / transcript / conversation)
- Ingestion timestamp
- URL or file path
- Metadata (author, date, title)

This enables full provenance auditing: any memory can be traced to its original source.

---

## Development Memory

### MemPalace Integration (Planned)

[MemPalace](https://github.com/your-org/mempalace) is the intended store for development memory.
Until it is fully integrated, development memory is maintained in:

- `docs/development_log.md` — running log of decisions, sessions, and notable events
- `docs/adr/` — Architecture Decision Records (one file per decision)
- Git commit messages — atomic change records

### Development Memory Content

| Category | Where stored |
|----------|-------------|
| Architecture decisions | `docs/adr/NNN-title.md` |
| Session summaries | `docs/development_log.md` |
| Bug post-mortems | `docs/development_log.md` |
| Prompt experiments | `docs/development_log.md` |
| Deployment notes | `docs/development_log.md` |

### Separation Guarantee

The `MemPalace` client (when integrated) must be initialized with a dedicated namespace key
(e.g., `dt_dev_memory`) that is different from and inaccessible to the Digital Twin runtime.
The Digital Twin runtime must not import or reference any `MemPalace` client code.

---

## Retrieval Design

### Digital Twin Retrieval Flow

```python
query_embedding = await llm.embed(user_message)
memories = await db.execute(
    select(MemoryItem)
    .where(MemoryItem.status == "active")
    .order_by(MemoryItem.embedding.cosine_distance(query_embedding))
    .limit(10)
)
```

Retrieved memories are injected into the prompt inside a clearly delimited context block.
See `docs/security.md` for the prompt template.

### Retrieval Filters

- `status = active` always applied
- `memory_type` filter optional (e.g., retrieve only `personality` memories for system prompt)
- `tags` filter optional
- `confidence >= threshold` filter optional (default 0.6)
- `subject_id` filter always applied to scope results to the represented person

---

## Deletion and Export

### Deletion

```
DELETE /api/v1/admin/memory/{id}

Result:
  MemoryItem.status = "deleted"
  MemoryItem.embedding = [0.0, 0.0, ...]  (zeroed)
  AuditLog entry written
```

Hard delete is not exposed in the API to preserve audit integrity. A separate database-level
purge procedure can be run by a DB admin if required.

### Export

```
GET /api/v1/admin/export

Result: GDPR-compatible JSON array of all MemoryItem records for subject_id
  AuditLog entry written with action = "export"
```
