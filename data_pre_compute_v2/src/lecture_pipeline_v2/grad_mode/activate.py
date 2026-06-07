"""Flip the whole lesson pipeline into graduate mode with ONE call.

`enable_graduate_mode()` swaps the three audience-bearing system prompts —
planner, judge, chapter planner — for graduate versions AT RUNTIME. It edits
NO files: it rebinds the prompt name inside each *consuming* module's namespace
(`lesson_planner`, `lesson_judge`, `chapter_planner`), which is the exact name
those modules read at call time (`from ... import NAME` binds NAME locally, and
the functions reference that local NAME). Rebinding it therefore changes what
they send to the LLM, while the canonical IGCSE prompt modules stay untouched.

Idempotent + reversible (`disable_graduate_mode()` restores the originals).

To bake graduate mode into the main pipeline permanently, this is the whole
"one-line change":

    from lecture_pipeline_v2.grad_mode import enable_graduate_mode
    enable_graduate_mode()

placed once before the lesson pipeline runs (e.g. top of `ingest-book`, or
gated behind a config flag). Nothing else moves.
"""

from __future__ import annotations

from lecture_pipeline_v2.curriculum.lecture_plan import (
    chapter_planner,
    lesson_judge,
    lesson_planner,
)
from lecture_pipeline_v2.grad_mode.grad_prompts import (
    GRADUATE_CHAPTER_PROMPT,
    GRADUATE_JUDGE_PROMPT,
    GRADUATE_LESSON_PROMPT,
)

# (consuming module, attribute name, graduate replacement)
_PATCHES = [
    (lesson_planner, "LESSON_PLANNING_SYSTEM_PROMPT", GRADUATE_LESSON_PROMPT),
    (lesson_judge, "LESSON_JUDGE_SYSTEM_PROMPT", GRADUATE_JUDGE_PROMPT),
    (chapter_planner, "CHAPTER_PLANNING_SYSTEM_PROMPT", GRADUATE_CHAPTER_PROMPT),
]

_originals: dict[str, object] = {}

# Per-topic context floor. Each topic is planned in its own fresh, single-shot
# LLM call (no accumulation -> no context rot), but the section source is clipped
# to 1500 chars inside _build_user_message — fine for a terse IGCSE section,
# starvation for a dense graduate one (Goodfellow 6.5 back-prop is ~6 pages, so
# 1500 chars is the first ~10%). We raise the floor so each topic sees its
# COMPLETE section. This is the difference between "summarize what you glimpsed"
# and "teach the whole mechanism".
_GRAD_CONTEXT_FLOOR = 16000


def _graduate_clip(text: str, max_chars: int) -> str:
    """Drop-in for lesson_planner._clip with a raised floor — same strip +
    ellipsis behaviour, just doesn't truncate a real section to a teaser."""
    text = text.strip()
    cap = max(max_chars, _GRAD_CONTEXT_FLOOR)
    if len(text) > cap:
        return text[:cap].rstrip() + "…"
    return text


def enable_graduate_mode() -> None:
    """Rebind planner/judge/chapter prompts to graduate versions AND raise the
    per-topic context floor (so dense sections aren't starved). Idempotent."""
    if _originals:
        return  # already enabled
    for module, attr, grad in _PATCHES:
        if not hasattr(module, attr):
            raise AttributeError(
                f"{module.__name__}.{attr} not found — the prompt import name "
                "changed; update grad_mode.activate._PATCHES."
            )
        _originals[f"{module.__name__}.{attr}"] = getattr(module, attr)
        setattr(module, attr, grad)
    # Raise the per-topic context floor so dense sections feed the planner whole.
    _originals["lesson_planner._clip"] = lesson_planner._clip
    lesson_planner._clip = _graduate_clip


def disable_graduate_mode() -> None:
    """Restore the original IGCSE prompts + the original context clip."""
    if not _originals:
        return
    for module, attr, _ in _PATCHES:
        setattr(module, attr, _originals[f"{module.__name__}.{attr}"])
    lesson_planner._clip = _originals["lesson_planner._clip"]
    _originals.clear()


def is_enabled() -> bool:
    return bool(_originals)
