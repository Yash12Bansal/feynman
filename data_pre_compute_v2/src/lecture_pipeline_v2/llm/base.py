"""Abstract base class for LLM providers.

Two capability tiers:

* **Sync** (`generate` / `generate_json`) — plain text/JSON. Used by the
  factory-path extraction stages (skeleton, topics, prereqs, questions,
  validation). Parallelism handled at the caller layer via `asyncio.to_thread`.
* **Async** (`agenerate_text` / `agenerate_tool_use` / `agenerate_vision`) —
  the capabilities the doc-19 lecture stack needs (async I/O, schema-forced
  structured output, image input). Each concrete cloud provider implements
  these natively; the base supplies portable fallbacks so a text-only provider
  (e.g. an Ollama judge) still works for text + emulated tool-use.

This is the SINGLE seam every ingestion LLM call flows through, so switching
`llm.provider` in config switches the whole pipeline.
"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from ..config import LLMConfig


@dataclass
class LLMResponse:
    content: str
    model: str
    usage: dict | None = None


class ProviderCapabilityError(NotImplementedError):
    """Raised when a provider is asked for a capability it lacks.

    The canonical case is vision on a text-only local model. Callers that can
    degrade gracefully (e.g. DiagramQA) should catch this and skip.
    """


class LLMProvider(ABC):
    """All providers expose sync generate / generate_json plus an async
    capability surface (text / tool_use / vision)."""

    def __init__(self, config: LLMConfig):
        self.config = config

    # ── sync surface (unchanged contract) ────────────────────────────────
    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse: ...

    @abstractmethod
    def generate_json(self, system_prompt: str, user_prompt: str) -> LLMResponse: ...

    # ── async capability surface ─────────────────────────────────────────
    async def agenerate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        """Async plain-text generation.

        Base fallback runs the sync `generate` in a worker thread. Cloud
        providers override with a native async client.
        """
        return await asyncio.to_thread(self.generate, system_prompt, user_prompt)

    async def agenerate_tool_use(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        tool_name: str,
        tool_description: str,
        input_schema: dict[str, Any],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any] | None:
        """Force the model to emit a JSON object matching `input_schema`.

        Returns the parsed object (the "tool input"), or None if nothing
        usable came back — callers Pydantic-validate the dict themselves.

        Base fallback EMULATES tool-use by injecting the schema into the
        prompt and using the provider's JSON mode. Providers with native
        function/tool calling (Anthropic, OpenAI, Gemini) override this for
        reliability; the fallback keeps text-only providers (Ollama judges)
        usable for structured output.
        """
        augmented_system = (
            f"{system_prompt}\n\n"
            f"{tool_description}\n\n"
            "You MUST respond with a SINGLE JSON object that validates against "
            "this JSON Schema — no prose, no markdown fences:\n"
            f"{json.dumps(input_schema)}"
        )
        resp = await asyncio.to_thread(
            self.generate_json, augmented_system, user_prompt
        )
        text = (resp.content or "").strip()
        if not text:
            return None
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    async def agenerate_vision(
        self,
        system_prompt: str,
        user_text: str,
        image_png: bytes,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        """Generate from a text+image prompt. Override in vision-capable
        providers; text-only providers raise ProviderCapabilityError."""
        raise ProviderCapabilityError(
            f"{type(self).__name__} (model={self.config.model!r}) does not "
            "support image input"
        )

    # ── helpers for subclasses ────────────────────────────────────────────
    def _max_tokens(self, max_tokens: int | None) -> int:
        return max_tokens if max_tokens is not None else self.config.max_tokens

    def _temp_kwargs(self, temperature: float | None) -> dict:
        """Splat-ready temperature kwarg.

        Returns ``{"temperature": t}`` only when a caller explicitly sets one,
        else ``{}`` — so the doc-19 async stages keep the provider SDK's own
        default (they never passed temperature historically). The sync
        text/JSON path still uses ``config.temperature`` as before. This keeps
        a provider swap a pure model swap, with no implicit temperature shift
        on the quality-critical lesson stages.
        """
        return {"temperature": temperature} if temperature is not None else {}
