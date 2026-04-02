"""Abstract base class for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..config import LLMConfig


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""
    content: str
    model: str
    usage: dict | None = None


class LLMProvider(ABC):
    """Abstract LLM provider interface.

    All providers must implement `generate` which takes a system prompt
    and user prompt and returns an LLMResponse.
    """

    def __init__(self, config: LLMConfig):
        self.config = config

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Generate a response from the LLM.

        Args:
            system_prompt: System-level instructions for the LLM.
            user_prompt: The user message / content to process.

        Returns:
            LLMResponse with the generated content.
        """
        ...

    @abstractmethod
    def generate_json(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Generate a JSON response from the LLM.

        Same as generate() but hints the model to return valid JSON.
        """
        ...
