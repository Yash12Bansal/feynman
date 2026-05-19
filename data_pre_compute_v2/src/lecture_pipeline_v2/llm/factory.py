"""Factory for creating LLM providers from config."""

from __future__ import annotations

from ..config import LLMConfig
from .anthropic_provider import AnthropicProvider
from .base import LLMProvider
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAIProvider


def create_llm_provider(config: LLMConfig) -> LLMProvider:
    if config.provider == "openai":
        return OpenAIProvider(config)
    if config.provider == "anthropic":
        return AnthropicProvider(config)
    if config.provider == "ollama":
        return OllamaProvider(config)
    raise ValueError(
        f"Unknown LLM provider: {config.provider!r}. "
        f"Supported: 'openai', 'anthropic', 'ollama'"
    )
