# ADR-003: LLM Provider Abstraction via BaseLLMProvider

**Status:** Accepted
**Date:** 2026-04-27

## Context

The system needs LLM capabilities (chat completion and text embedding) from multiple
potential backends:
- Anthropic Claude (cloud, preferred for production)
- OpenAI GPT (cloud, enterprise alternative)
- Ollama / vLLM (local, for privacy or offline deployments)

Without abstraction, swapping providers requires changes throughout the codebase.
Additionally, provider-specific logic (retry, rate limiting, credential handling) tends
to leak into business logic.

## Decision

Define a `BaseLLMProvider` abstract class in `src/llm/base.py` with two methods:
- `complete(messages, **kwargs) -> LLMResponse`
- `embed(text) -> EmbeddingResponse`

Concrete implementations:
- `AnthropicProvider` — uses `anthropic` SDK
- `OpenAIProvider` — uses `openai` SDK
- `LocalLLMProvider` — uses HTTP calls to Ollama/vLLM OpenAI-compatible API

Provider is selected at startup via `LLM_PROVIDER` environment variable.
All business logic imports only `BaseLLMProvider`.

## Consequences

- Adding a new LLM backend requires only a new class in `src/llm/`
- Prompt injection defenses are enforced once in the base class, not per provider
- Testing can use a mock provider implementing `BaseLLMProvider`
- Embedding dimension varies by provider/model; stored in config to prevent schema mismatch
