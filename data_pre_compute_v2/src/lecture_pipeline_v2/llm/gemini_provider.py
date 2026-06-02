"""Google Gemini provider (google-genai SDK).

Sync text/JSON + async text/tool-use(function-calling)/vision(inline image).

`google-genai` is imported LAZILY: the factory imports this module
unconditionally, but a machine that never selects the gemini provider should
not be forced to have the SDK installed. A clear error is raised on first use
if it's missing.

Schema note: Gemini's function-declaration schema rejects the `$ref`/`$defs`/
`anyOf` that Pydantic emits — `_schema_gemini.to_gemini_schema` downconverts
to the supported subset. See that module for the gory details.
"""

from __future__ import annotations

from typing import Any

from ..config import LLMConfig
from ._schema_gemini import to_gemini_schema
from .base import LLMProvider, LLMResponse

_INSTALL_HINT = (
    "google-genai is not installed. It is a core dependency — run "
    "`poetry install` in data_pre_compute_v2 (or `pip install google-genai`) "
    "to use the gemini provider."
)


class GeminiProvider(LLMProvider):
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client_obj: Any = None

    def _client(self) -> Any:
        if self._client_obj is None:
            try:
                from google import genai
            except ImportError as exc:  # pragma: no cover - env-dependent
                raise ImportError(_INSTALL_HINT) from exc
            self._client_obj = genai.Client(api_key=self.config.api_key or None)
        return self._client_obj

    @staticmethod
    def _types() -> Any:
        try:
            from google.genai import types
        except ImportError as exc:  # pragma: no cover - env-dependent
            raise ImportError(_INSTALL_HINT) from exc
        return types

    # ── sync ──────────────────────────────────────────────────────────────
    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        types = self._types()
        resp = self._client().models.generate_content(
            model=self.config.model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=self.config.temperature,
                max_output_tokens=self.config.max_tokens,
            ),
        )
        return LLMResponse(
            content=resp.text or "", model=self.config.model, usage=_usage(resp)
        )

    def generate_json(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        types = self._types()
        resp = self._client().models.generate_content(
            model=self.config.model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=self.config.temperature,
                max_output_tokens=self.config.max_tokens,
                response_mime_type="application/json",
            ),
        )
        return LLMResponse(
            content=resp.text or "", model=self.config.model, usage=_usage(resp)
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
        types = self._types()
        resp = await self._client().aio.models.generate_content(
            model=self.config.model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=self._max_tokens(max_tokens),
                **self._temp_kwargs(temperature),
            ),
        )
        return LLMResponse(
            content=resp.text or "", model=self.config.model, usage=_usage(resp)
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
        types = self._types()
        declaration = types.FunctionDeclaration(
            name=tool_name,
            description=tool_description,
            parameters=to_gemini_schema(input_schema),
        )
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=self._max_tokens(max_tokens),
            tools=[types.Tool(function_declarations=[declaration])],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode="ANY",
                    allowed_function_names=[tool_name],
                )
            ),
            **self._temp_kwargs(temperature),
        )
        resp = await self._client().aio.models.generate_content(
            model=self.config.model, contents=user_prompt, config=config
        )
        for call in _function_calls(resp):
            if call.name == tool_name and call.args is not None:
                return dict(call.args)
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
        types = self._types()
        resp = await self._client().aio.models.generate_content(
            model=self.config.model,
            contents=[
                types.Part.from_text(text=user_text),
                types.Part.from_bytes(data=image_png, mime_type="image/png"),
            ],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=self._max_tokens(max_tokens),
                **self._temp_kwargs(temperature),
            ),
        )
        return LLMResponse(
            content=resp.text or "", model=self.config.model, usage=_usage(resp)
        )


def _function_calls(resp: Any) -> list[Any]:
    """Pull every function_call part out of a Gemini response, defensively."""
    calls: list[Any] = []
    for candidate in getattr(resp, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            fc = getattr(part, "function_call", None)
            if fc is not None:
                calls.append(fc)
    return calls


def _usage(resp: Any) -> dict | None:
    meta = getattr(resp, "usage_metadata", None)
    if meta is None:
        return None
    return {
        "input_tokens": getattr(meta, "prompt_token_count", 0) or 0,
        "output_tokens": getattr(meta, "candidates_token_count", 0) or 0,
    }
