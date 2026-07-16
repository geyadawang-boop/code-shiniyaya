"""
clients/__init__.py — LLMClient unified adapter factory.

Provides:
  LLMClientFactory.create(provider, **kwargs) → BaseLLMClient
  Streaming/non-streaming dual-mode unified interface.

Usage:
  from clients import create_llm_client
  client = create_llm_client("anthropic", api_key="...", model="claude-opus-4-8")
  result = await client.chat(messages, max_tokens=4096, stream=False)
"""

from .base import BaseLLMClient
from .anthropic_client import AnthropicClient
from .openai_client import OpenAIClient
from .deepseek_client import DeepSeekClient

PROVIDER_REGISTRY = {
    "anthropic": AnthropicClient,
    "claude": AnthropicClient,
    "openai": OpenAIClient,
    "deepseek": DeepSeekClient,
}


def create_llm_client(
    provider: str,
    api_key: str = "",
    api_url: str = "",
    model: str = "",
    **kwargs,
) -> BaseLLMClient:
    """
    Factory: returns the correct LLMClient subclass for the given provider.

    Detection priority:
      1. Explicit provider arg (anthropic|openai|deepseek)
      2. URL-based heuristic: "anthropic.com" → anthropic, "deepseek" → deepseek
      3. Fallback → OpenAIClient (OpenAI-compatible wire protocol)
    """
    if provider in PROVIDER_REGISTRY:
        cls = PROVIDER_REGISTRY[provider]
        return cls(api_key=api_key, api_url=api_url, model=model, **kwargs)

    # URL-based heuristic
    url_lower = (api_url or "").lower()
    if "anthropic.com" in url_lower:
        return AnthropicClient(api_key=api_key, api_url=api_url, model=model, **kwargs)
    if "deepseek.com" in url_lower:
        return DeepSeekClient(api_key=api_key, api_url=api_url, model=model, **kwargs)

    # Default: OpenAI-compatible
    return OpenAIClient(api_key=api_key, api_url=api_url, model=model, **kwargs)


__all__ = [
    "BaseLLMClient",
    "AnthropicClient",
    "OpenAIClient",
    "DeepSeekClient",
    "create_llm_client",
    "PROVIDER_REGISTRY",
]
