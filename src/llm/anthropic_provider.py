"""
Anthropic Claude provider.

Uses the `anthropic` SDK. API key is injected at construction time from config —
never hardcoded.
"""

import logging
from typing import Optional

from src.llm.base import BaseLLMProvider, EmbeddingResponse, LLMMessage, LLMResponse

logger = logging.getLogger(__name__)

# Default model names — override via config if needed
_DEFAULT_CHAT_MODEL = "claude-sonnet-4-6"
_DEFAULT_EMBED_MODEL = "voyage-3"  # 1024-dim — matches dt_memory_items.embedding column


class AnthropicProvider(BaseLLMProvider):
    def __init__(
        self,
        api_key: Optional[str] = None,
        voyage_api_key: Optional[str] = None,
        chat_model: str = _DEFAULT_CHAT_MODEL,
        embed_model: str = _DEFAULT_EMBED_MODEL,
    ) -> None:
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic"
            )
        # Import lazily so the package is optional when using other providers
        try:
            import anthropic as _anthropic

            self._client = _anthropic.AsyncAnthropic(api_key=api_key)
        except ImportError as exc:
            raise ImportError(
                "Install the `anthropic` package to use AnthropicProvider"
            ) from exc
        self._chat_model = chat_model
        self._embed_model = embed_model
        self._voyage_api_key = voyage_api_key

    async def complete(
        self,
        messages: list[LLMMessage],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        **kwargs,
    ) -> LLMResponse:
        system_parts = [m.content for m in messages if m.role == "system"]
        user_parts = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role != "system"
        ]
        system_text = "\n\n".join(system_parts) if system_parts else None

        response = await self._client.messages.create(
            model=self._chat_model,
            max_tokens=max_tokens,
            system=system_text,
            messages=user_parts,
            temperature=temperature,
            **kwargs,
        )
        content = response.content[0].text if response.content else ""
        return LLMResponse(
            content=content,
            model=response.model,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        )

    async def embed(self, text: str) -> EmbeddingResponse:
        if not self._voyage_api_key:
            raise ValueError(
                "VOYAGE_API_KEY is required for embeddings with AnthropicProvider"
            )

        try:
            import voyageai as _voyageai
        except ImportError as exc:
            raise ImportError(
                "Install the `voyageai` package to use embeddings with AnthropicProvider"
            ) from exc

        client = _voyageai.AsyncClient(api_key=self._voyage_api_key)

        response = await client.embed(
            texts=[text],
            model=self._embed_model,
        )
        embedding = response.embeddings[0]
        return EmbeddingResponse(
            embedding=embedding,
            model=self._embed_model,
        )
