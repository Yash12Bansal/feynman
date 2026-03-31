"""Bridge to the design_agent diagram generator.

Reads the design agent's system prompt and calls Claude directly
to generate full SVG-based DiagramSpec dictionaries. This produces
much higher quality diagrams than the structured node/edge approach.

The design_agent source lives at ``<project_root>/design_agent/backend/``.
We read its prompt at runtime so changes to the prompt propagate automatically.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import anthropic
import structlog

logger = structlog.get_logger()

# ── Prompt loading ─────────────────────────────────────────

_PROMPT_FILE = Path(__file__).resolve().parents[4] / "design_agent" / "backend" / "prompts.py"

_cached_prompt: str | None = None


def _load_system_prompt() -> str:
    """Read SYSTEM_PROMPT from the design_agent prompts module."""
    global _cached_prompt
    if _cached_prompt is not None:
        return _cached_prompt

    if not _PROMPT_FILE.exists():
        raise FileNotFoundError(
            f"design_agent prompts not found at {_PROMPT_FILE}. "
            "Ensure the design_agent directory is present in the project root."
        )

    ns: dict[str, Any] = {}
    exec(compile(_PROMPT_FILE.read_text(), _PROMPT_FILE, "exec"), ns)  # noqa: S102
    _cached_prompt = ns["SYSTEM_PROMPT"]
    return _cached_prompt


# ── JSON extraction & repair (ported from design_agent) ────

_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)


def _extract_json(text: str) -> str:
    """Return the JSON payload from *text*, stripping optional markdown fences."""
    match = _CODE_FENCE_RE.search(text)
    if match:
        return match.group(1).strip()

    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]

    return text


def _repair_json(json_str: str) -> dict[str, Any] | None:
    """Try to repair truncated JSON by closing open brackets/braces."""
    s = json_str.rstrip()
    s = re.sub(r",\s*$", "", s)
    s = re.sub(r',?\s*"[^"]*"\s*:\s*$', "", s)
    s = re.sub(r',?\s*"[^"]*"\s*:\s*"[^"]*$', "", s)
    s = re.sub(r",?\s*\{[^}]*$", "", s)

    opens = 0
    open_sq = 0
    in_string = False
    escape = False
    for ch in s:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            opens += 1
        elif ch == "}":
            opens -= 1
        elif ch == "[":
            open_sq += 1
        elif ch == "]":
            open_sq -= 1

    s += "]" * max(0, open_sq)
    s += "}" * max(0, opens)

    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


def _parse_response(raw_text: str) -> dict[str, Any]:
    """Extract JSON from the model output, validate structure, and return dict."""
    json_str = _extract_json(raw_text)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        data = _repair_json(json_str)
        if data is None:
            logger.error(
                "design_bridge.json_parse_failed",
                chars=len(json_str),
                preview=json_str[:500],
            )
            raise ValueError("Claude returned invalid/truncated JSON for diagram.")

    # Basic structural validation
    if not isinstance(data, dict) or "elements" not in data:
        raise ValueError("Response missing required 'elements' field.")

    return data


# ── Model mapping ──────────────────────────────────────────

_MODELS = {
    "opus": "claude-opus-4-20250514",
    "sonnet": "claude-sonnet-4-20250514",
    "haiku": "claude-haiku-4-5-20251001",
}

# ── Public API ─────────────────────────────────────────────

_async_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _async_client
    if _async_client is None:
        from feynman.config import settings

        _async_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _async_client


async def generate_design_diagram(
    prompt: str,
    model: str = "sonnet",
    max_tokens: int = 16000,
) -> dict[str, Any]:
    """Generate a DiagramSpec using the design agent prompt.

    Args:
        prompt: Natural language description of the diagram to draw.
        model: Claude model key ("opus", "sonnet", "haiku").
        max_tokens: Maximum response tokens.

    Returns:
        A validated DiagramSpec dict with elements, title, etc.
    """
    system_prompt = _load_system_prompt()
    model_id = _MODELS.get(model, model)
    client = _get_client()

    logger.info("design_bridge.generating", prompt=prompt[:100], model=model_id)

    accumulated = ""
    async with client.messages.stream(
        model=model_id,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        async for text in stream.text_stream:
            accumulated += text

        final = await stream.get_final_message()
        if final.stop_reason == "max_tokens":
            logger.warning(
                "design_bridge.truncated",
                chars=len(accumulated),
            )

    spec = _parse_response(accumulated)
    _save_spec(spec, prompt)
    logger.info(
        "design_bridge.complete",
        title=spec.get("title", ""),
        elements=len(spec.get("elements", [])),
    )
    return spec


# ── Spec persistence ───────────────────────────────────────

_GENERATED_DIR = Path(__file__).resolve().parents[4] / "design_agent" / "generated"


def _save_spec(spec: dict[str, Any], prompt: str) -> None:
    """Save the diagram spec alongside the design_agent's generated files."""
    try:
        _GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        title = spec.get("title", "untitled")
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", title).strip("_").lower()[:50]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{slug}.json"
        filepath = _GENERATED_DIR / filename
        filepath.write_text(json.dumps({"prompt": prompt, "spec": spec}, indent=2))
        logger.debug("design_bridge.saved", path=str(filepath))
    except Exception:
        logger.warning("design_bridge.save_failed", exc_info=True)
