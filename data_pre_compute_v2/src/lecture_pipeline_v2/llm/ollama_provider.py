"""Ollama provider — runs local open-weight models for the multi-model judge.

Ollama exposes a native `format="json"` option for JSON-mode generation,
which is more reliable than prompt-only JSON coercion.
"""

from __future__ import annotations

import ollama

from ..config import LLMConfig
from .base import LLMProvider, LLMResponse


class OllamaProvider(LLMProvider):
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        host = config.base_url or "http://localhost:11434"
        self.client = ollama.Client(host=host)

    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        response = self.client.chat(
            model=self.config.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            options={
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            },
        )
        return LLMResponse(
            content=response["message"]["content"],
            model=response.get("model", self.config.model),
            usage={
                "input_tokens": response.get("prompt_eval_count", 0),
                "output_tokens": response.get("eval_count", 0),
            },
        )

    def generate_json(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        response = self.client.chat(
            model=self.config.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            format="json",
            options={
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            },
        )
        return LLMResponse(
            content=response["message"]["content"],
            model=response.get("model", self.config.model),
            usage={
                "input_tokens": response.get("prompt_eval_count", 0),
                "output_tokens": response.get("eval_count", 0),
            },
        )
