"""OpenAI-compatible provider (also vLLM / OpenAI-compatible endpoints).

Sync text/JSON + async text/tool-use(function-calling)/vision(image_url).
"""

from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI, OpenAI

from ..config import LLMConfig
from .base import LLMProvider, LLMResponse


class OpenAIProvider(LLMProvider):
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        kwargs: dict[str, Any] = {}
        if config.api_key:
            kwargs["api_key"] = config.api_key
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self._client_kwargs = kwargs
        self.client = OpenAI(**kwargs)
        self._aclient: AsyncOpenAI | None = None

    @property
    def aclient(self) -> AsyncOpenAI:
        if self._aclient is None:
            self._aclient = AsyncOpenAI(**self._client_kwargs)
        return self._aclient

    # ── sync ──────────────────────────────────────────────────────────────
    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )
        return _text_response(response, self.config.model)

    def generate_json(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            response_format={"type": "json_object"},
        )
        return _text_response(response, self.config.model)

    # ── async ─────────────────────────────────────────────────────────────
    async def agenerate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        response = await self.aclient.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            **self._temp_kwargs(temperature),
            max_tokens=self._max_tokens(max_tokens),
        )
        return _text_response(response, self.config.model)

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
        response = await self.aclient.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            **self._temp_kwargs(temperature),
            max_tokens=self._max_tokens(max_tokens),
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "description": tool_description,
                        "parameters": input_schema,
                    },
                }
            ],
            tool_choice={"type": "function", "function": {"name": tool_name}},
        )
        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None) or []
        for call in tool_calls:
            if call.function.name == tool_name:
                try:
                    data = json.loads(call.function.arguments or "{}")
                except (json.JSONDecodeError, ValueError):
                    return None
                return data if isinstance(data, dict) else None
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
        response = await self.aclient.chat.completions.create(
            model=self.config.model,
            max_tokens=self._max_tokens(max_tokens),
            **self._temp_kwargs(temperature),
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                    ],
                },
            ],
        )
        return _text_response(response, self.config.model)


def _text_response(response: Any, fallback_model: str) -> LLMResponse:
    choice = response.choices[0]
    usage = None
    if getattr(response, "usage", None):
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }
    return LLMResponse(
        content=choice.message.content or "",
        model=getattr(response, "model", fallback_model),
        usage=usage,
    )
