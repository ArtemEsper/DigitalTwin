# ADR-002: Strict Two-Namespace Memory Separation

**Status:** Accepted
**Date:** 2026-04-27

## Context

The project maintains two categories of memory:
1. Digital Twin Memory — personal data about the represented person
2. Development Memory — project implementation history and decisions

If these are mixed, risks include:
- Development notes contaminating the agent's personality/factual responses
- Personal data leaking into development tooling / logs
- Inability to delete personal data independently of project history
- Regulatory exposure (GDPR) from commingled personal/operational data

## Decision

Enforce strict namespace separation at **three independent layers**:

### Layer 1: Database Schema
- All Digital Twin tables use the `dt_` prefix
- Development memory is stored externally (MemPalace or dev tooling)
- No foreign keys or joins cross the namespace boundary

### Layer 2: Code Structure
- Digital Twin memory operations live in `src/memory/`
- No `src/memory/` module imports any development-memory client
- No development-memory client imports any `src/memory/` module
- Tests explicitly verify no cross-namespace calls occur

### Layer 3: Runtime Isolation
- Digital Twin runtime containers receive no MemPalace credentials
- Development memory tooling receives no `DATABASE_URL` for the DT database

## Consequences

- Slightly more infrastructure to manage (two memory stores)
- Clearer data boundaries make GDPR compliance straightforward
- Independent deletion/export of personal data is trivially implementable
- Development insights about the project cannot accidentally surface in agent responses
