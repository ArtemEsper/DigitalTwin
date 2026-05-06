from src.llm.base import BaseLLMProvider, EmbeddingResponse, LLMMessage, LLMResponse
from src.llm.anthropic_provider import AnthropicProvider
from src.llm.openai_provider import OpenAIProvider
from src.llm.local_provider import LocalLLMProvider
from src.config import settings


def get_llm_provider() -> BaseLLMProvider:
    """Factory: returns the configured LLM provider."""
    provider = settings.LLM_PROVIDER.lower()
    if provider == "anthropic":
        return AnthropicProvider(
            api_key=settings.ANTHROPIC_API_KEY,
            voyage_api_key=settings.VOYAGE_API_KEY,
        )
    if provider == "openai":
        return OpenAIProvider(api_key=settings.OPENAI_API_KEY)
    if provider == "local":
        return LocalLLMProvider(
            base_url=settings.LOCAL_LLM_BASE_URL,
            model=settings.LOCAL_LLM_MODEL,
            embed_model=settings.LOCAL_EMBED_MODEL,
        )
    raise ValueError(f"Unknown LLM_PROVIDER: {settings.LLM_PROVIDER!r}")


__all__ = [
    "BaseLLMProvider",
    "LLMMessage",
    "LLMResponse",
    "EmbeddingResponse",
    "AnthropicProvider",
    "OpenAIProvider",
    "LocalLLMProvider",
    "get_llm_provider",
]
