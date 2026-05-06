"""
Local LLM provider via Ollama / vLLM (OpenAI-compatible API).

No API key required — uses base URL only.
"""

import logging

import httpx

from src.llm.base import BaseLLMProvider, EmbeddingResponse, LLMMessage, LLMResponse

logger = logging.getLogger(__name__)


class LocalLLMProvider(BaseLLMProvider):
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3",
        embed_model: str = "nomic-embed-text",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._embed_model = embed_model

    async def complete(
        self,
        messages: list[LLMMessage],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        **kwargs,
    ) -> LLMResponse:
        # Ollama OpenAI-compatible endpoint
        payload = {
            "model": self._model,
            "messages": [
                {"role": m.role, "content": m.content} for m in messages
            ],
            "options": {"num_predict": max_tokens, "temperature": temperature},
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self._base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        content = (
            data.get("message", {}).get("content", "")
            or data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        return LLMResponse(
            content=content,
            model=self._model,
            usage={},
        )

    async def embed(self, text: str) -> EmbeddingResponse:
        payload = {"model": self._embed_model, "prompt": text}
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self._base_url}/api/embeddings",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        embedding: list[float] = data.get("embedding", [])
        return EmbeddingResponse(embedding=embedding, model=self._embed_model)
