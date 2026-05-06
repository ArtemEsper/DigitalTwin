# Digital Twin System — Security Design

## Threat Model

### External Threats

| Threat | Description |
|--------|------------|
| Prompt injection | Adversarial content in channel messages that attempts to manipulate the agent's memory or override system instructions |
| Unauthorized memory writes | Channel participants attempting to implant false or harmful memories |
| Credential leakage | LLM API keys or database credentials exposed in logs, images, or committed code |
| Unauthorized channel access | Unauthenticated callers triggering ingest or admin endpoints |
| Memory poisoning via bulk ingest | Large volumes of crafted documents injected during ingestion |

### Internal / Structural Threats

| Threat | Description |
|--------|------------|
| Memory namespace collision | Development/Claude Code memory leaking into Digital Twin memory via shared tables or retrieval paths |
| Automatic unreviewed learning | Background processes promoting unreviewed `MemoryCandidate` records to long-term memory |
| Privilege escalation via channel | A `read_only_chat` channel user attempting admin operations |

---

## Defensive Boundaries

### 1. Input Sanitization

- All inbound channel messages are treated as **untrusted strings**
- Content is stored verbatim in `RawSource` / `ConversationMessage` but is **never** interpolated directly into LLM system prompts
- Memory retrieval results are clearly delimited from user instructions using structured prompt templates:

```
[SYSTEM INSTRUCTIONS — authoritative]
You are representing {name}. Answer based on the memories below.

[MEMORY CONTEXT — retrieved, may contain user-generated content]
{memory_block}
[END MEMORY CONTEXT]

[USER MESSAGE — untrusted]
{user_message}
[END USER MESSAGE]
```

- The LLM wrapper enforces this template; raw user strings are **never** concatenated to the system section

### 2. Credential Management

- No API keys stored in code or Docker images
- All secrets provided via environment variables at runtime
- `.env.example` contains only placeholder values; `.env` is gitignored
- Runtime containers receive only the secrets they need (principle of least privilege)
- Admin API key is distinct from channel API keys

### 3. Memory Write Authorization Policy

| Permission Level | Can trigger memory write? |
|-----------------|--------------------------|
| `read_only_chat` | No — responses only |
| `learn_candidate` | Creates `MemoryCandidate` (pending) only |
| `admin` | Can approve/reject candidates → promotes to `MemoryItem` |

- Policy is evaluated by `ChannelGateway` **before any processing**
- Unknown channels/users receive `403 Forbidden` immediately
- The approval step requires an additional `X-Admin-Key` header

### 4. Audit Logging

Every memory operation writes an `AuditLog` record with:

| Field | Description |
|-------|------------|
| `actor` | Channel ID / user ID / system |
| `action` | `read` \| `write` \| `delete` \| `approve` \| `reject` \| `export` |
| `target_type` | `MemoryItem` \| `MemoryCandidate` \| `RawSource` |
| `target_id` | UUID of the affected record |
| `metadata` | JSONB with request context |
| `created_at` | Immutable timestamp |

- The audit table has no `UPDATE` or `DELETE` ORM methods exposed
- Audit entries are never accessible to channel-level permissions

### 5. Allowlist-Based Authorization

- `ChannelConfig` stores per-channel permission level
- `allowed_user_ids` array restricts which senders within a channel may trigger operations
- An empty `allowed_user_ids` means the entire channel is authorized at its permission level
- Inbound messages from unknown channels are rejected before any processing

### 6. Prompt Injection Defense

- Retrieved memory items are wrapped in a delimited context block
- User-supplied content is placed **after** system instructions with a clear boundary
- LLM provider wrappers validate that the `system` role message contains the delimiter before sending
- No f-string or `.format()` interpolation of untrusted content into system prompts

---

## Data Privacy

- Every `MemoryItem` has a `status` field: `active` | `deleted` | `exported`
- Deletion sets `status = deleted` and zeroes the embedding vector; hard delete is not performed to preserve audit integrity
- Export API (`GET /api/v1/admin/export`) returns a GDPR-compatible JSON dump of all `MemoryItem` records for the subject
- `RawSource` content may be separately purged via `DELETE /api/v1/admin/sources/{id}`

---

## Security Checklist

- [ ] `.env` listed in `.gitignore`
- [ ] No secrets in `Dockerfile` or `docker-compose.yml`
- [ ] All channel messages validated before LLM calls
- [ ] `AuditLog` has no `update` / `delete` methods exposed
- [ ] Admin endpoints require `X-Admin-Key` header
- [ ] Memory write path always passes through candidate review
- [ ] Prompt templates enforce `[MEMORY CONTEXT]` / `[USER MESSAGE]` delimiters
- [ ] pgvector queries use SQLAlchemy parameterized statements only
- [ ] `allowed_user_ids` checked before processing per-channel messages
- [ ] Embedding dimension validated on ingest to prevent shape mismatch injection
