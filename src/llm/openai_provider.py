"""
OpenAI GPT / text-embedding provider.
"""

import logging
from typing import Optional

from src.llm.base import BaseLLMProvider, EmbeddingResponse, LLMMessage, LLMResponse

logger = logging.getLogger(__name__)

_DEFAULT_CHAT_MODEL = "gpt-4o"
_DEFAULT_EMBED_MODEL = "text-embedding-3-small"
_DEFAULT_EMBED_DIM = 1536


class OpenAIProvider(BaseLLMProvider):
    def __init__(
        self,
        api_key: Optional[str] = None,
        chat_model: str = _DEFAULT_CHAT_MODEL,
        embed_model: str = _DEFAULT_EMBED_MODEL,
    ) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        try:
            import openai as _openai

            self._client = _openai.AsyncOpenAI(api_key=api_key)
        except ImportError as exc:
            raise ImportError(
                "Install the `openai` package to use OpenAIProvider"
            ) from exc
        self._chat_model = chat_model
        self._embed_model = embed_model

    async def complete(
        self,
        messages: list[LLMMessage],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        **kwargs,
    ) -> LLMResponse:
        openai_messages = [
            {"role": m.role, "content": m.content} for m in messages
        ]
        response = await self._client.chat.completions.create(
            model=self._chat_model,
            messages=openai_messages,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )
        choice = response.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            },
        )

    async def embed(self, text: str) -> EmbeddingResponse:
        response = await self._client.embeddings.create(
            model=self._embed_model,
            input=text,
        )
        embedding = response.data[0].embedding
        return EmbeddingResponse(
            embedding=embedding,
            model=self._embed_model,
        )
