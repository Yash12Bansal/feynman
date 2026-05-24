"""Abstract base class for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..config import LLMConfig


@dataclass
class LLMResponse:
    content: str
    model: str
    usage: dict | None = None


class LLMProvider(ABC):
    """All providers expose synchronous generate / generate_json.

    Parallelism is handled at the caller layer via asyncio.to_thread,
    matching v1's pattern.
    """

    def __init__(self, config: LLMConfig):
        self.config = config

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        ...

    @abstractmethod
    def generate_json(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        ...
