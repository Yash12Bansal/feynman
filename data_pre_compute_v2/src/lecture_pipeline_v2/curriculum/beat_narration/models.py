"""Phase 4d — BeatNarration Pydantic model.

One per `TeachingBeat` whose `BeatNarrationWriter.write_one()` was invoked.
Carries the marker-embedded narration string, the estimated speech duration,
and lightweight QA telemetry (`audio_targets`, `needs_review`).

Layout:
  * `beat_id` is positional — `f"{topic_id}_b{beat_index}"`. Same convention
    as Phase 4c's `Diagram.linked_beat_id`, so the two join naturally.
  * `text` is "" when the writer failed; downstream stages must tolerate it.
  * `audio_targets` is a side-effect telemetry field — regex-extracted from
    `text` post-generation, listing every marker id the narration references.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BeatNarration(BaseModel):
    beat_id: str = Field(..., description="Format: '{topic_id}_b{beat_index}'")
    topic_id: str
    beat_index: int = Field(..., ge=0)
    beat_type: str = Field(
        ...,
        description=(
            "hook | big_picture | first_principles | bridge | visual_build | "
            "explain | derive | ask | misconception | example | summarize | transition"
        ),
    )
    text: str = Field(
        default="",
        description="Spoken narration with inline markers; '' if generation failed",
    )
    target_duration_seconds: int = Field(..., ge=0)
    estimated_duration_seconds: float = Field(default=0.0, ge=0.0)
    audio_targets: list[str] = Field(
        default_factory=list,
        description="Marker IDs referenced (eq-1, key-2, ...) — telemetry only",
    )
    needs_review: bool = False
    # Book-coverage USP: source of the example beat (mirror of TeachingBeat
    # fields). Set ONLY when beat_type == "example". Used by the coverage
    # validator to confirm every Topic.book_examples produced a beat.
    example_source: Literal["book", "extended"] | None = None
    book_example_ref: int | None = None
