"""LessonProsody — doc 19 Phase G voice prosody applicator.

Deterministic pass over a `TopicNarration` (Phase E output) that places
prosody pauses based on per-segment flags:

- `is_question=True`      → `<<PAUSE:long>>` after the narration (the
                            curiosity-hang doc 19 §5 calls for).
- `is_payoff=True`        → `<<PAUSE:short>>` before the narration (the
                            beat-before-the-click).
- `presses_crucial_fact`  → `<<PAUSE:short>>` after the narration (the
                            fact-landing pause, so it doesn't blur into
                            the next sentence).

Kokoro (`tts/kokoro_provider.py`) does not accept SSML or rate / pitch /
emphasis params — doc 19 explicitly anticipates this and falls back to
"chunked-segment volume/rate variation". Phase G v0 keeps the implementation
minimal: pure pause placement, which covers ~80% of perceived prosody. The
audio-DSP fallback (per-fragment volume scaling via pydub) is Phase G.5
work, out of scope here.

Idempotent: Phase E inserts a fixed `<<PAUSE:short>>` after every
`is_question=True` step as a v0 placeholder. Phase G strips that trailing
marker before reapplying its own choice, so calling `apply` twice
produces the same result as calling it once.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from lecture_pipeline_v2.curriculum.lecture_plan.lesson_narrator import (
    LessonNarrationSegment,
    TopicNarration,
)


# Regexes that match leading / trailing PAUSE markers plus surrounding
# whitespace. Used to strip Phase E's hardcoded question-pause AND any
# pause this applicator added on a prior run before Phase G re-applies
# its own prosody — re-running prosody on already-prosodied text is a no-op.
_TRAILING_PAUSE_RE = re.compile(r"\s*<<PAUSE:(?:short|long)>>\s*$")
_LEADING_PAUSE_RE = re.compile(r"^\s*<<PAUSE:(?:short|long)>>\s*")


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────


class ProsodyConfig(BaseModel):
    """Phase G v0 prosody knobs. Defaults are tuned for the Aanya-demo bar
    (question-hang clearly longer than the inter-step beat; payoff and
    press both get a deliberate-but-not-jarring micro-pause)."""

    enabled: bool = Field(
        default=True,
        description="When False, `apply` returns the input unchanged.",
    )
    question_pause: Literal["short", "long"] = Field(
        default="long",
        description="Pause duration after `is_question=True` steps.",
    )
    payoff_pre_pause: Literal["short", "long", "none"] = Field(
        default="short",
        description="Pause duration BEFORE `is_payoff=True` steps. 'none' "
        "disables the prefix pause.",
    )
    press_post_pause: Literal["short", "long", "none"] = Field(
        default="short",
        description="Pause duration AFTER `presses_crucial_fact=True` steps "
        "that are NOT also `is_question` (question pause wins). 'none' "
        "disables the suffix pause.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Applicator
# ─────────────────────────────────────────────────────────────────────────────


class LessonProsody:
    """Stateless prosody applicator. One instance can process many narrations."""

    def __init__(self, config: ProsodyConfig | None = None) -> None:
        self.config = config or ProsodyConfig()

    def apply(self, narration: TopicNarration) -> TopicNarration:
        """Return a new TopicNarration with prosody pauses placed per the
        config. Disabled config → input returned unchanged (same object)."""
        if not self.config.enabled:
            return narration

        new_segments: list[LessonNarrationSegment] = []
        for seg in narration.segments:
            updated_text = _apply_to_segment(seg, self.config)
            new_segments.append(
                seg.model_copy(update={"text_with_markers": updated_text})
            )

        full = " ".join(
            s.text_with_markers for s in new_segments if s.text_with_markers
        )
        return narration.model_copy(
            update={
                "segments": new_segments,
                "full_text_with_markers": full,
            }
        )


# ─────────────────────────────────────────────────────────────────────────────
# Module-level helpers (kept at module scope so tests can hit them directly).
# ─────────────────────────────────────────────────────────────────────────────


def _apply_to_segment(segment: LessonNarrationSegment, config: ProsodyConfig) -> str:
    """Compute the new `text_with_markers` for one segment.

    Walks the priority list:
      1. Strip Phase E's trailing PAUSE AND any leading PAUSE the applicator
         added on a previous run (idempotency).
      2. Prepend payoff-pre-pause if applicable.
      3. Append question-pause if applicable (wins over press-pause).
      4. Else append press-post-pause if applicable.
    """
    text = _strip_leading_pause_marker(
        _strip_trailing_pause_marker(segment.text_with_markers)
    ).strip()

    prefix_parts: list[str] = []
    suffix_parts: list[str] = []

    if segment.is_payoff and config.payoff_pre_pause != "none":
        prefix_parts.append(f"<<PAUSE:{config.payoff_pre_pause}>>")

    if segment.is_question:
        suffix_parts.append(f"<<PAUSE:{config.question_pause}>>")
    elif segment.presses_crucial_fact and config.press_post_pause != "none":
        suffix_parts.append(f"<<PAUSE:{config.press_post_pause}>>")

    parts = prefix_parts + ([text] if text else []) + suffix_parts
    return " ".join(parts).strip()


def _strip_trailing_pause_marker(text: str) -> str:
    """Remove a single trailing `<<PAUSE:short>>` or `<<PAUSE:long>>` plus
    any surrounding whitespace. Returns the input unchanged if no such
    marker is present."""
    return _TRAILING_PAUSE_RE.sub("", text)


def _strip_leading_pause_marker(text: str) -> str:
    """Remove a single leading `<<PAUSE:short>>` or `<<PAUSE:long>>` plus
    any surrounding whitespace. Used for idempotency — a prior `apply` may
    have prepended a payoff-pre-pause; re-applying must not double it."""
    return _LEADING_PAUSE_RE.sub("", text)
