"""Pydantic models for the Phase 4 doubt-resolution pipeline.

`ResolutionPlan` is the central output — a list of beats the worker will
deliver in Phase 5. Each beat carries narration text, a free-text visual
intent (what kind of visual would help), and a list of typed annotation
actions that map 1:1 to the doc-19 manifest event types so Phase 5
delivery can publish them through the existing visuals contract.

`ChapterContext` is the in-memory snapshot of a chapter's topics +
diagrams loaded from Neo4j once per lecture session.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from feynman_teaching_kernel.style_guide import BANNED_OPENERS
from pydantic import BaseModel, Field, field_validator

from feynman.agent.doubt_resolution.doubt_classifier import DoubtClassification

# Phase 6: banned phrases the doubt planner should never emit. The
# `BANNED_OPENERS` list from the shared kernel covers generic teaching
# openers ("Let's", "Now,", "Great", "Okay", etc.); we extend it with
# doubt-specific service-bot phrases the planner kept slipping into
# during dogfood.
_DOUBT_EXTRA_BANNED: list[str] = [
    "I'm happy to help",
    "I see what you're asking",
    "Of course",
    "Sure",
    "Let me start by",
    "Let me explain",
    "Let me think",
    "Building on that",
    "First of all",
    "Umm",
    "Uhh",
    "Ah,",
    "Hmm",
    "Well,",
    "Great question",
    "That's a great question",
    "Wonderful",
    "I love that",
    "You're absolutely right",
]
_ALL_BANNED_OPENERS: tuple[str, ...] = tuple(
    p.lower() for p in (*BANNED_OPENERS, *_DOUBT_EXTRA_BANNED)
)

# ── Annotation actions (one per type, discriminated union) ──────────────────


class FocusAction(BaseModel):
    """Spotlight an element on the active diagram (or release on null)."""

    action: Literal["focus"] = "focus"
    target_element_id: str | None = None
    target_role: str | None = None
    text: str | None = None  # optional inline label


class PointAtAction(BaseModel):
    """Draw a pointer arrow at an element."""

    action: Literal["point_at"] = "point_at"
    element_id: str
    from_side: Literal["top", "bottom", "left", "right"] = "left"


class TraceAction(BaseModel):
    """Animate a tracing stroke over a path element."""

    action: Literal["trace"] = "trace"
    element_id: str
    duration_ms: int = 1500


class MarkPointAction(BaseModel):
    """Drop a marker at (x, y) in the diagram's SVG coordinates."""

    action: Literal["mark_point"] = "mark_point"
    x: float
    y: float
    kind: Literal["dot", "cross", "star"] = "dot"
    label: str = ""


AnnotationAction = Annotated[
    FocusAction | PointAtAction | TraceAction | MarkPointAction,
    Field(discriminator="action"),
]


# ── Resolution beats + plan ─────────────────────────────────────────────────


class ResolutionBeat(BaseModel):
    """One narration + visual unit. Phase 5 delivers beats sequentially."""

    narration_text: str
    visual_intent_description: str
    annotation_actions: list[AnnotationAction] = Field(default_factory=list)
    # Filled by DiagramFitMatcher — None when no precomputed diagram fits.
    target_diagram_id: str | None = None

    @field_validator("narration_text")
    @classmethod
    def _narration_non_empty(cls, v: str) -> str:
        text = v.strip()
        if not text:
            raise ValueError("narration_text must be non-empty")
        # Phase 6: enforce the persona at the validator level so the
        # planner's 2-attempt retry can re-prompt when the LLM ignores the
        # banned-opener instruction. We check the opening run of the
        # narration (case-insensitive, ignoring trailing punctuation
        # variants the LLM may slip in).
        normalised = text.lower().lstrip("\"'`*")
        for phrase in _ALL_BANNED_OPENERS:
            if normalised.startswith(phrase):
                raise ValueError(
                    f"narration_text starts with a banned opener "
                    f"({phrase!r}). Rewrite without filler or flattery."
                )
        return text


class ResolutionPlan(BaseModel):
    """The doubt-resolution planner's full output."""

    beats: list[ResolutionBeat] = Field(..., min_length=1, max_length=6)


# ── Diagram fit verifier ────────────────────────────────────────────────────


class FitVerdict(BaseModel):
    """Haiku verifier's judgement on a single (diagram, beat) pair."""

    fits: bool
    confidence: float = Field(..., ge=0.0, le=1.0)
    rationale: str = ""


# ── Session-only doubt history ──────────────────────────────────────────────


class DoubtRecord(BaseModel):
    """One row in `LectureDoubtSession.prior_doubts_in_session`."""

    doubt_text: str
    classification: DoubtClassification
    plan_summary: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)


# ── Chapter context (loaded once per lecture session) ───────────────────────


class TopicMeta(BaseModel):
    """The slice of a Topic node the doubt pipeline reads."""

    topic_id: str
    topic_name: str
    section_number: str = ""
    summary: str = ""


class DiagramData(BaseModel):
    """The slice of a Diagram node the matcher reads.

    `dictionary` keeps the doc-19 per-element semantic map (role / semantic
    / position / spatial_relations / bounds). Stored as `dict[str, dict]`
    rather than a typed nested model because the matcher only inspects
    the role + semantic strings, and the full Phase H shape varies.
    """

    diagram_id: str
    description: str = ""
    dictionary: dict[str, dict[str, Any]] = Field(default_factory=dict)
    linked_topic_ids: list[str] = Field(default_factory=list)


class ChapterContext(BaseModel):
    """Hydrated chapter snapshot for one lecture session."""

    chapter_id: str
    title: str = ""
    topics: dict[str, TopicMeta] = Field(default_factory=dict)
    diagrams: dict[str, DiagramData] = Field(default_factory=dict)

    def topic(self, topic_id: str | None) -> TopicMeta | None:
        if topic_id is None:
            return None
        return self.topics.get(topic_id)

    def adjacent_topics(self, topic_id: str | None, *, radius: int = 1) -> list[TopicMeta]:
        """Return the ±radius topics around `topic_id` in section order.

        Used by the planner to give the LLM a sense of what came before and
        what comes next, so it can position the resolution in the lesson
        arc without re-reading the whole chapter.
        """
        if not topic_id or not self.topics:
            return []
        ordered = sorted(self.topics.values(), key=lambda t: t.section_number)
        try:
            idx = next(i for i, t in enumerate(ordered) if t.topic_id == topic_id)
        except StopIteration:
            return []
        lo = max(0, idx - radius)
        hi = min(len(ordered), idx + radius + 1)
        return [t for t in ordered[lo:hi] if t.topic_id != topic_id]
