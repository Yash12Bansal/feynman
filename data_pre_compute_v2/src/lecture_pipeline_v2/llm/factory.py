"""Factory for creating LLM providers from config.

The SINGLE switch: `config.provider` picks the implementation, and every
ingestion stage builds its client through here, so changing the provider in
config.yaml (or via a per-role override) changes the whole pipeline.
"""

from __future__ import annotations

from ..config import LLMConfig
from .anthropic_provider import AnthropicProvider
from .base import LLMProvider
from .gemini_provider import GeminiProvider
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAIProvider


def create_llm_provider(config: LLMConfig) -> LLMProvider:
    if config.provider == "openai":
        return OpenAIProvider(config)
    if config.provider == "anthropic":
        return AnthropicProvider(config)
    if config.provider == "ollama":
        return OllamaProvider(config)
    if config.provider == "gemini":
        return GeminiProvider(config)
    raise ValueError(
        f"Unknown LLM provider: {config.provider!r}. "
        f"Supported: 'openai', 'anthropic', 'ollama', 'gemini'"
    )
