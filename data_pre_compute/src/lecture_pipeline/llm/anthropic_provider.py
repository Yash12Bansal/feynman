"""Anthropic (Claude) LLM provider."""

from __future__ import annotations

import json

from anthropic import Anthropic

from ..config import LLMConfig
from .base import LLMProvider, LLMResponse


class AnthropicProvider(LLMProvider):
    """Provider for Anthropic's Claude API."""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        kwargs = {}
        if config.api_key:
            kwargs["api_key"] = config.api_key
        self.client = Anthropic(**kwargs)

    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        response = self.client.messages.create(
            model=self.config.model,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )
        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        return LLMResponse(
            content=content,
            model=response.model,
            usage=usage,
        )

    def generate_json(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        # Claude doesn't have a native JSON mode, so we instruct it via prompt
        json_system = (
            system_prompt
            + "\n\nIMPORTANT: You MUST respond with valid JSON only. "
            "No markdown fences, no extra text — just the JSON object."
        )
        response = self.generate(json_system, user_prompt)
        # Strip any accidental markdown fences
        content = response.content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            # Remove first and last fence lines
            lines = [l for l in lines if not l.strip().startswith("```")]
            content = "\n".join(lines).strip()
        return LLMResponse(
            content=content,
            model=response.model,
            usage=response.usage,
        )
