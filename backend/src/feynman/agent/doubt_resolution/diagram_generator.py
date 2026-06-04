"""Real-time diagram generation for doubt resolution.

When a doubt needs a visual that no precomputed diagram can resolve, the planner
emits a `generate` directive with a brief. This module turns that brief into a
`DesignDiagramSpec` — the SAME shape the precompute pipeline produces, including
the semantic `dictionary` the annotation layer requires — so a generated doubt
diagram renders and annotates identically to a precomputed lecture one.

Prompt source: the canonical design-agent system prompt, disk-loaded from
`design_agent/backend/prompts.py` (the human-edited source the precompute
pipeline syncs from verbatim). Loading it at runtime keeps one source of truth
and guarantees the generated spec carries a populated `dictionary`.

Latency: a from-scratch spec takes several seconds. Callers MUST overlap this
with narration (start generation when planning finishes; await per-beat during
delivery) so it never blocks time-to-first-voice. See `lecture_session`.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import anthropic
import structlog

from feynman.config import settings

logger = structlog.get_logger()

# Sonnet for quality — a doubt diagram must be correct, not just fast. Latency
# is hidden behind narration by the caller, not by downgrading the model.
_MODEL = "claude-sonnet-4-20250514"
_MAX_TOKENS = 8192
_DEFAULT_WIDTH = 900
_DEFAULT_HEIGHT = 650


def _load_design_system_prompt() -> str | None:
    """Disk-load `SYSTEM_PROMPT` from design_agent/backend/prompts.py.

    Repo layout: this file is
    backend/src/feynman/agent/doubt_resolution/diagram_generator.py, so the repo
    root is parents[5]. Returns None if the file is missing/unreadable — the
    generator then degrades to "no diagram" rather than crashing the doubt.
    """
    try:
        repo_root = Path(__file__).resolve().parents[5]
        prompt_path = repo_root / "design_agent" / "backend" / "prompts.py"
        spec = importlib.util.spec_from_file_location(
            "_design_agent_prompts", prompt_path
        )
        if spec is None or spec.loader is None:
            logger.warning("diagram_generator.prompt_spec_none", path=str(prompt_path))
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        prompt = getattr(module, "SYSTEM_PROMPT", None)
        if isinstance(prompt, str) and prompt.strip():
            return prompt
        logger.warning("diagram_generator.prompt_empty", path=str(prompt_path))
        return None
    except Exception:
        logger.warning("diagram_generator.prompt_load_failed", exc_info=True)
        return None


_SYSTEM_PROMPT = _load_design_system_prompt()


def _extract_text(response: Any) -> str:
    parts: list[str] = []
    for block in getattr(response, "content", None) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


def _parse_json(raw: str) -> dict[str, Any] | None:
    """Tolerant JSON extraction — strips code fences, slices first…last brace."""
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        # ```json\n{...}\n```  →  {...}
        fenced = text.split("```")
        if len(fenced) >= 2:
            body = fenced[1]
            text = body[4:] if body.lstrip().startswith("json") else body
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


async def generate_doubt_diagram(
    *,
    brief: str,
    title: str = "",
    client: anthropic.AsyncAnthropic | None = None,
) -> dict[str, Any] | None:
    """Generate a DesignDiagramSpec (with dictionary) from a brief.

    Returns the spec dict (ready to ship inline to the frontend as
    `chapter.diagrams[id].spec`) or None on any failure — callers degrade the
    beat to "no diagram" rather than stalling the doubt.
    """
    if not _SYSTEM_PROMPT:
        logger.warning("diagram_generator.no_prompt")
        return None
    if not brief or not brief.strip():
        return None

    user_message = brief.strip() if not title else f"{title.strip()}\n\n{brief.strip()}"
    client = client or anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key or "")

    try:
        response = await client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
    except Exception:
        logger.warning("diagram_generator.api_error", exc_info=True)
        return None

    spec = _parse_json(_extract_text(response))
    if not isinstance(spec, dict) or not isinstance(spec.get("elements"), list):
        logger.warning("diagram_generator.invalid_spec")
        return None

    if not isinstance(spec.get("dictionary"), dict) or not spec["dictionary"]:
        # The diagram still renders, but annotations have nothing to anchor to.
        # Loud, never silent — this is exactly the kind of gap that read as
        # "annotations broken" before.
        logger.warning("diagram_generator.no_dictionary", title=title)

    # Defensive defaults so the frontend's viewBox math never divides by undef.
    spec.setdefault("width", _DEFAULT_WIDTH)
    spec.setdefault("height", _DEFAULT_HEIGHT)
    if title and not spec.get("title"):
        spec["title"] = title
    return spec
