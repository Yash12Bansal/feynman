"""Anthropic (Claude) LLM provider — sync text/JSON + async text/tool-use/vision."""

from __future__ import annotations

from typing import Any

from anthropic import Anthropic, AsyncAnthropic

from ..config import LLMConfig
from .base import LLMProvider, LLMResponse

# Newer Claude generations (e.g. Opus 4.8) deprecate the `temperature` parameter
# and reject any request that sets it with a 400. We omit temperature for these
# models and keep sending it for ones that still accept it. Matched by prefix so
# dated snapshots (…-YYYYMMDD) are covered too.
_TEMPERATURE_UNSUPPORTED_PREFIXES = ("claude-opus-4-8",)


class AnthropicProvider(LLMProvider):
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        kwargs: dict[str, Any] = {}
        if config.api_key:
            kwargs["api_key"] = config.api_key
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self._client_kwargs = kwargs
        self.client = Anthropic(**kwargs)
        self._aclient: AsyncAnthropic | None = None

    @property
    def aclient(self) -> AsyncAnthropic:
        # Lazily built so sync-only callers never construct an async client.
        if self._aclient is None:
            self._aclient = AsyncAnthropic(**self._client_kwargs)
        return self._aclient

    def _supports_temperature(self) -> bool:
        # Some newer Claude models reject the temperature param entirely.
        return not self.config.model.startswith(_TEMPERATURE_UNSUPPORTED_PREFIXES)

    def _temp_kwargs(self, temperature: float | None) -> dict:
        # Model-aware override: drop temperature for models that deprecate it,
        # even if a caller passed one explicitly; otherwise defer to the base.
        if not self._supports_temperature():
            return {}
        return super()._temp_kwargs(temperature)

    # ── sync ──────────────────────────────────────────────────────────────
    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        response = self.client.messages.create(
            model=self.config.model,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=self.config.max_tokens,
            **self._temp_kwargs(self.config.temperature),
        )
        content = "".join(
            block.text for block in response.content if block.type == "text"
        )
        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        return LLMResponse(content=content, model=response.model, usage=usage)

    def generate_json(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        # Claude has no native JSON mode — instruct in prompt and strip fences.
        json_system = (
            system_prompt + "\n\nIMPORTANT: You MUST respond with valid JSON only. "
            "No markdown fences, no extra text — just the JSON object."
        )
        response = self.generate(json_system, user_prompt)
        return LLMResponse(
            content=_strip_fences(response.content),
            model=response.model,
            usage=response.usage,
        )

    # ── async ─────────────────────────────────────────────────────────────
    async def agenerate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        response = await self.aclient.messages.create(
            model=self.config.model,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            **self._temp_kwargs(temperature),
            max_tokens=self._max_tokens(max_tokens),
        )
        content = "".join(
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text"
        )
        return LLMResponse(
            content=content,
            model=getattr(response, "model", self.config.model),
            usage=_usage(response),
        )

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
        response = await self.aclient.messages.create(
            model=self.config.model,
            max_tokens=self._max_tokens(max_tokens),
            **self._temp_kwargs(temperature),
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            tools=[
                {
                    "name": tool_name,
                    "description": tool_description,
                    "input_schema": input_schema,
                }
            ],
            tool_choice={"type": "tool", "name": tool_name},
        )
        for block in response.content:
            if (
                getattr(block, "type", None) == "tool_use"
                and getattr(block, "name", None) == tool_name
            ):
                payload = block.input
                return payload if isinstance(payload, dict) else None
        return None

    async def agenerate_vision(
        self,
        system_prompt: str,
        user_text: str,
        image_png: bytes,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        import base64

        b64 = base64.standard_b64encode(image_png).decode("ascii")
        response = await self.aclient.messages.create(
            model=self.config.model,
            max_tokens=self._max_tokens(max_tokens),
            **self._temp_kwargs(temperature),
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": user_text},
                    ],
                }
            ],
        )
        content = "".join(
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text"
        )
        return LLMResponse(
            content=content,
            model=getattr(response, "model", self.config.model),
            usage=_usage(response),
        )


def _strip_fences(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        lines = [
            line for line in content.split("\n") if not line.strip().startswith("```")
        ]
        content = "\n".join(lines).strip()
    return content


def _usage(response: Any) -> dict | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    return {
        "input_tokens": getattr(usage, "input_tokens", 0),
        "output_tokens": getattr(usage, "output_tokens", 0),
    }
