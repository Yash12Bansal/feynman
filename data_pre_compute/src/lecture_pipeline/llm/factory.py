"""Factory for creating LLM providers from config."""

from __future__ import annotations

from ..config import LLMConfig
from .base import LLMProvider
from .openai_provider import OpenAIProvider
from .anthropic_provider import AnthropicProvider


def create_llm_provider(config: LLMConfig) -> LLMProvider:
    """Create an LLM provider based on config.

    Args:
        config: LLM configuration specifying provider, model, etc.

    Returns:
        An initialized LLMProvider instance.

    Raises:
        ValueError: If provider is not recognized.
    """
    if config.provider == "openai":
        return OpenAIProvider(config)
    elif config.provider == "anthropic":
        return AnthropicProvider(config)
    else:
        raise ValueError(
            f"Unknown LLM provider: {config.provider!r}. "
            f"Supported: 'openai', 'anthropic'"
        )
