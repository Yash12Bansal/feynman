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
from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class RevealStepAction(BaseModel):
    """Advance a build_up diagram's staged reveal (or jump to group `step`)."""

    action: Literal["reveal_step"] = "reveal_step"
    step: int = 0


class SetParameterAction(BaseModel):
    """Jump a parametric diagram's parameter to a value."""

    action: Literal["set_parameter"] = "set_parameter"
    name: str
    value: float


class AnimateParameterAction(BaseModel):
    """Sweep a parameter while narrating — the sweep IS the explanation.

    `from_` is authored + serialized as `from` (a Python keyword).
    """

    model_config = ConfigDict(populate_by_name=True)

    action: Literal["animate_parameter"] = "animate_parameter"
    name: str
    to: float
    from_: float | None = Field(default=None, alias="from")
    duration_ms: int | None = None


AnnotationAction = Annotated[
    FocusAction
    | PointAtAction
    | TraceAction
    | MarkPointAction
    | RevealStepAction
    | SetParameterAction
    | AnimateParameterAction,
    Field(discriminator="action"),
]


# ── Diagram directive — the planner's per-beat reuse-vs-generate decision ────
#
# A doubt resolution is a real-time mini-lecture. For every beat the planner
# decides what visual the board should carry. It chooses from a faithful
# semantic catalog of the chapter's diagrams (see `resolution_planner`), so the
# call is informed, not a guess: REUSE an existing precomputed diagram when one
# explains the point with complete clarity, GENERATE a brand-new diagram when
# none is sufficient, KEEP whatever is already on the doubt board, or NONE for a
# pure narration / notebook beat.


class ReuseDiagram(BaseModel):
    """Reuse a precomputed diagram that already resolves this beat clearly."""

    mode: Literal["reuse"] = "reuse"
    diagram_id: str = Field(
        ...,
        description=(
            "EXACT id of one of the AVAILABLE DIAGRAMS listed in the prompt. "
            "Only reuse when that diagram lets you explain this beat with "
            "complete clarity."
        ),
    )


class GenerateDiagram(BaseModel):
    """Generate a brand-new diagram from scratch for this beat."""

    mode: Literal["generate"] = "generate"
    brief: str = Field(
        ...,
        description=(
            "A precise, self-contained description of the NEW diagram to draw "
            "— what it depicts, the key labelled parts, and the spatial layout "
            "— enough for an illustrator to render it without the doubt text. "
            "Use ONLY when no available diagram suffices."
        ),
    )
    title: str = Field(default="", description="Short title shown above the slide.")


class KeepDiagram(BaseModel):
    """Keep whatever diagram is already on the doubt board (annotate it further)."""

    mode: Literal["keep"] = "keep"


class NoDiagram(BaseModel):
    """This beat needs no diagram — narration and/or notebook writing only."""

    mode: Literal["none"] = "none"


class TemplateDiagram(BaseModel):
    """Show a canonical, hand-built figure INSTANTLY (zero-LLM, <1 frame).

    Prefer this over `generate` whenever the figure IS one of the AVAILABLE
    TEMPLATES — it appears immediately. `concept_id` must be one of those ids
    (an unknown id degrades to no-diagram at resolve time); `params` optionally
    sets the figure's parameters, e.g. {"theta": 30}.
    """

    mode: Literal["template"] = "template"
    concept_id: str = Field(..., description="A canonical template id from AVAILABLE TEMPLATES.")
    params: dict[str, float] = Field(default_factory=dict)


DiagramDirective = Annotated[
    ReuseDiagram | GenerateDiagram | TemplateDiagram | KeepDiagram | NoDiagram,
    Field(discriminator="mode"),
]


# ── Notebook writes — author content; ids are assigned at compile time ───────


class WriteEquationBlock(BaseModel):
    block: Literal["equation"] = "equation"
    latex: str = Field(..., description="KaTeX-renderable LaTeX, no surrounding $.")
    boxed: bool = Field(default=False, description="Box the equation to emphasise a result.")
    align_group: str | None = Field(
        default=None,
        description="Equations sharing a group align their '=' signs.",
    )


class WriteStepBlock(BaseModel):
    block: Literal["step"] = "step"
    text: str
    indent: int = Field(default=0, ge=0, le=3)


class WriteTextBlock(BaseModel):
    block: Literal["text"] = "text"
    text: str


class WriteKeyPointBlock(BaseModel):
    block: Literal["key_point"] = "key_point"
    text: str = Field(..., description="One crisp takeaway, highlighted in the notebook.")


class WriteSectionBlock(BaseModel):
    block: Literal["section"] = "section"
    title: str


NotebookWrite = Annotated[
    WriteEquationBlock | WriteStepBlock | WriteTextBlock | WriteKeyPointBlock | WriteSectionBlock,
    Field(discriminator="block"),
]


# ── Resolution beats + plan ─────────────────────────────────────────────────


class ResolutionBeat(BaseModel):
    """One narration + board unit of a doubt resolution. Delivered sequentially.

    A beat is a mini-lecture moment: Feynman says `narration_text` while the
    board carries the beat's visual — a diagram (reused / generated / kept),
    notebook writing, and annotations on top. The deterministic compiler
    (`doubt_resolution.board_events`) turns a beat into the same `ManifestEvent`
    vocabulary the precompute lecture uses, so the frontend plays it through
    the identical path on a separate doubt board.
    """

    narration_text: str
    diagram: DiagramDirective = Field(
        default_factory=NoDiagram,
        description=(
            "What this beat's slide should show. Reuse an available diagram, "
            "generate a new one, keep the current doubt-board diagram, or none."
        ),
    )
    notebook_writes: list[NotebookWrite] = Field(
        default_factory=list,
        description=(
            "Lines to write into the doubt notebook this beat (equations, "
            "steps, key points) — exactly as the lecture writes its notebook."
        ),
    )
    annotation_actions: list[AnnotationAction] = Field(default_factory=list)
    # DEPRECATED (kept until the matcher path is removed): the planner used to
    # emit a free-text intent and leave the diagram to a downstream matcher.
    # The planner now decides the diagram directly via `diagram` above.
    visual_intent_description: str = ""
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
    # Idea 3 — adjacency list used by `prereq_walker.walk_prereqs` to BFS
    # backward through the curriculum graph. List of topic_ids the current
    # topic strictly depends on. Empty for foundational topics.
    prereq_topic_ids: list[str] = Field(default_factory=list)


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
    # Mirrors v2 Diagram.presentation_mode so a reused diagram keeps its show
    # mode on the doubt board. Defaults overview (a recap shows the complete
    # figure); not yet persisted on the Diagram node, so old data loads as
    # overview until re-ingested.
    presentation_mode: Literal["build_up", "overview"] = "overview"


# Idea 2 — mirror of v2's VisualTermEntry, duck-typed across the project
# boundary. We accept whatever extra fields the v2 schema adds and only
# require the four we actually consume.
class VisualTermEntry(BaseModel):
    diagram_id: str
    element_id: str
    role: str = ""
    semantic: str = ""
    linked_beat_id: str = ""


class ChapterContext(BaseModel):
    """Hydrated chapter snapshot for one lecture session."""

    chapter_id: str
    title: str = ""
    topics: dict[str, TopicMeta] = Field(default_factory=dict)
    diagrams: dict[str, DiagramData] = Field(default_factory=dict)
    visual_index: list[VisualTermEntry] = Field(default_factory=list)

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
