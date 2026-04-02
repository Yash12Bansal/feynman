"""Diagram generation agent — calls Claude or local models (via Ollama) to produce a DiagramSpec from a text prompt."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

import anthropic
import httpx

from prompts import SYSTEM_PROMPT
from schema import DiagramSpec

logger = logging.getLogger(__name__)

# Pre-compiled pattern to strip markdown code fences from Claude responses.
_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)


def _extract_json(text: str) -> str:
    """Return the JSON payload from *text*, stripping optional markdown fences."""
    match = _CODE_FENCE_RE.search(text)
    if match:
        return match.group(1).strip()

    # Try to find a raw JSON object in the response.
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]

    return text


class DiagramAgent:
    """Generates diagram specifications by prompting Claude or Ollama models."""

    AVAILABLE_MODELS = {
        "opus": "claude-opus-4-20250514",
        "sonnet": "claude-sonnet-4-20250514",
        "haiku": "claude-haiku-4-5-20251001",
    }

    def __init__(
        self,
        model: str = "opus",
        max_tokens: int = 16000,
        provider: str | None = None,
        ollama_base_url: str | None = None,
    ) -> None:
        self.default_model = model
        self.max_tokens = max_tokens

        # Provider: "anthropic" (default) or "ollama"
        self.provider = provider or os.environ.get("DESIGN_AGENT_PROVIDER", "anthropic")
        self.ollama_base_url = (
            ollama_base_url
            or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        ).rstrip("/")

        if self.provider == "anthropic":
            self.client = anthropic.Anthropic()
            self.async_client = anthropic.AsyncAnthropic()
        else:
            self.client = None
            self.async_client = None

    def _resolve_model(self, model: str | None) -> str:
        key = model or self.default_model
        if self.provider == "anthropic":
            return self.AVAILABLE_MODELS.get(key, key)
        # For Ollama, pass the model name through directly
        return key

    # ------------------------------------------------------------------
    # Synchronous interface
    # ------------------------------------------------------------------

    def generate_sync(self, prompt: str, model: str | None = None) -> dict:
        """Blocking call — routes to Anthropic or Ollama based on provider."""
        if self.provider == "ollama":
            return self._generate_ollama_sync(prompt, model)
        return self._generate_anthropic_sync(prompt, model)

    def _generate_anthropic_sync(self, prompt: str, model: str | None = None) -> dict:
        """Blocking call using Anthropic streaming."""
        accumulated = ""
        with self.client.messages.stream(
            model=self._resolve_model(model),
            max_tokens=self.max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                accumulated += text
        return self._parse(accumulated)

    def _generate_ollama_sync(self, prompt: str, model: str | None = None) -> dict:
        """Blocking call using Ollama API."""
        resolved = self._resolve_model(model)
        logger.info("Generating diagram via Ollama (model=%s)", resolved)
        response = httpx.post(
            f"{self.ollama_base_url}/api/chat",
            json={
                "model": resolved,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "options": {"num_predict": self.max_tokens, "temperature": 0.3},
            },
            timeout=180.0,
        )
        response.raise_for_status()
        data = response.json()
        raw_text = data["message"]["content"]
        if data.get("done_reason") == "length":
            logger.warning("Ollama response truncated (%d chars).", len(raw_text))
        return self._parse(raw_text)

    # ------------------------------------------------------------------
    # Async interface
    # ------------------------------------------------------------------

    async def generate(self, prompt: str, model: str | None = None) -> dict:
        """Async call — routes to Anthropic or Ollama based on provider."""
        if self.provider == "ollama":
            return await self._generate_ollama_async(prompt, model)
        return await self._generate_anthropic_async(prompt, model)

    async def _generate_anthropic_async(self, prompt: str, model: str | None = None) -> dict:
        """Async call using Anthropic streaming."""
        accumulated = ""
        async with self.async_client.messages.stream(
            model=self._resolve_model(model),
            max_tokens=self.max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            async for text in stream.text_stream:
                accumulated += text
            final = await stream.get_final_message()
            if final.stop_reason == "max_tokens":
                logger.warning("Response truncated (max_tokens). Accumulated %d chars.", len(accumulated))
        return self._parse(accumulated)

    async def _generate_ollama_async(self, prompt: str, model: str | None = None) -> dict:
        """Async call using Ollama API."""
        resolved = self._resolve_model(model)
        logger.info("Generating diagram via Ollama async (model=%s)", resolved)
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                f"{self.ollama_base_url}/api/chat",
                json={
                    "model": resolved,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "options": {"num_predict": self.max_tokens, "temperature": 0.3},
                },
            )
            response.raise_for_status()
            data = response.json()
        raw_text = data["message"]["content"]
        if data.get("done_reason") == "length":
            logger.warning("Ollama response truncated (%d chars).", len(raw_text))
        return self._parse(raw_text)

    async def generate_stream(self, prompt: str, model: str | None = None):
        """Async generator that yields partial text chunks."""
        if self.provider == "ollama":
            async for chunk in self._stream_ollama(prompt, model):
                yield chunk
        else:
            async for chunk in self._stream_anthropic(prompt, model):
                yield chunk

    async def _stream_anthropic(self, prompt: str, model: str | None = None):
        async with self.async_client.messages.stream(
            model=self._resolve_model(model),
            max_tokens=self.max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def _stream_ollama(self, prompt: str, model: str | None = None):
        resolved = self._resolve_model(model)
        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream(
                "POST",
                f"{self.ollama_base_url}/api/chat",
                json={
                    "model": resolved,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": True,
                    "options": {"num_predict": self.max_tokens, "temperature": 0.3},
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        yield content

    def parse_response(self, raw_text: str) -> DiagramSpec:
        """Parse raw accumulated text into a validated DiagramSpec."""
        return self._parse(raw_text)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _repair_json(json_str: str) -> dict | None:
        """Try to repair truncated JSON by closing open brackets/braces."""
        # Strip trailing incomplete key-value pairs
        import re
        s = json_str.rstrip()
        # Remove trailing comma or incomplete value
        s = re.sub(r',\s*$', '', s)
        # Remove incomplete key-value like `"key": ` at the end
        s = re.sub(r',?\s*"[^"]*"\s*:\s*$', '', s)
        # Remove incomplete string value like `"key": "partial...` at the end
        s = re.sub(r',?\s*"[^"]*"\s*:\s*"[^"]*$', '', s)
        # Remove incomplete object start like `{  "type":` at the end
        s = re.sub(r',?\s*\{[^}]*$', '', s)

        # Count open brackets and close them
        opens = 0
        open_sq = 0
        in_string = False
        escape = False
        for ch in s:
            if escape:
                escape = False
                continue
            if ch == '\\':
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                opens += 1
            elif ch == '}':
                opens -= 1
            elif ch == '[':
                open_sq += 1
            elif ch == ']':
                open_sq -= 1

        # Close any open brackets
        s += ']' * max(0, open_sq)
        s += '}' * max(0, opens)

        try:
            data = json.loads(s)
            logger.info("Repaired truncated JSON successfully (%d elements)", len(data.get("elements", [])))
            return data
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _fix_latex_escapes(json_str: str) -> str:
        """Fix single-backslash LaTeX commands that break JSON parsing.

        In JSON, \\f is form-feed, \\b is backspace, \\t is tab, etc.
        Claude sometimes writes \\frac instead of \\\\frac in JSON strings.
        We fix these by doubling backslashes before known LaTeX commands.
        """
        import re
        # Match single backslash followed by a LaTeX command (not already double-escaped)
        # Only inside string values (between quotes)
        latex_cmds = (
            r"frac|int|sum|prod|left|right|sqrt|vec|hat|bar|dot|ddot|"
            r"theta|alpha|beta|gamma|delta|epsilon|lambda|omega|pi|sigma|phi|mu|nu|"
            r"sin|cos|tan|log|ln|exp|lim|inf|sup|min|max|"
            r"text|mathrm|mathbf|mathit|operatorname|"
            r"cdot|times|div|pm|mp|leq|geq|neq|approx|equiv|"
            r"Big|big|Bigg|bigg|"
            r"partial|nabla|forall|exists|in|"
            r"begin|end|quad|qquad|,"
        )
        # Replace \cmd with \\cmd, but only if not already \\cmd
        pattern = r'(?<!\\)\\(' + latex_cmds + r')'

        def _double_escape(m: re.Match) -> str:
            return '\\\\' + m.group(1)

        return re.sub(pattern, _double_escape, json_str)

    @staticmethod
    def _parse(raw_text: str) -> dict:
        """Extract JSON from the model output, validate, and return the raw dict."""
        json_str = _extract_json(raw_text)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            # Try to repair truncated JSON by closing open brackets
            data = DiagramAgent._repair_json(json_str)
            if data is None:
                logger.error("Failed to parse JSON (%d chars). First 500: %s", len(json_str), json_str[:500])
                raise ValueError("Claude returned invalid/truncated JSON. Try a simpler prompt.")

        # Validate schema (raises on error) but return the raw dict
        # to avoid Pydantic discriminated union serialization warnings
        try:
            DiagramSpec.model_validate(data)
        except Exception as exc:
            logger.error("Schema validation failed for data:\n%s", json.dumps(data, indent=2)[:2000])
            raise ValueError(f"Diagram spec validation error: {exc}") from exc

        return data
