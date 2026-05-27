"""Canonical models for the v2 curriculum pipeline.

The schema is intentionally small: Chapter / Topic / Diagram / Question +
manifest events for playback. Every field listed has a clear runtime use
case — subjective fields (difficulty_level, estimated_duration_s) were
dropped on purpose.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, model_validator

if TYPE_CHECKING:
    from feynman_teaching_kernel import ConceptTeachingPlan

    from lecture_pipeline_v2.curriculum.beat_narration.models import BeatNarration
    from lecture_pipeline_v2.curriculum.lecture_plan.lesson_narrator import (
        TopicNarration,
    )
    from lecture_pipeline_v2.curriculum.lecture_plan.lesson_plan_models import (
        LessonPlan,
    )
    from lecture_pipeline_v2.curriculum.lecture_plan.models import ChapterLecturePlan


# ---------------------------------------------------------------------------
# Geometry primitives (Phase 3 — precompute-lecture-overhaul)
# ---------------------------------------------------------------------------


class Rect(BaseModel):
    """Axis-aligned rectangle in page coordinates (pixels)."""

    x: float
    y: float
    width: float
    height: float


class Placement(BaseModel):
    """Resolved page-coordinate placement of a notebook block or slide diagram."""

    page_index: int = Field(..., ge=0)
    rect: Rect
    measured: bool = False


# ---------------------------------------------------------------------------
# Manifest events — the playback contract between pipeline and runtime
# ---------------------------------------------------------------------------


class AudioEvent(BaseModel):
    type: Literal["audio"] = "audio"
    url: str = Field(..., description="Reachable URL/URI for the audio file")
    duration_ms: int = Field(..., ge=0)


class PauseEvent(BaseModel):
    type: Literal["pause"] = "pause"
    duration_ms: int = Field(..., ge=0)


class ShowDiagramEvent(BaseModel):
    type: Literal["show_diagram"] = "show_diagram"
    diagram_id: str
    # Phase 3: optional. Slide placement (page-coord rect) of the diagram and
    # per-role page-coord bounds of dictionary elements. Frontend's live-DOM
    # resolver still works without these; they're forward-compat for a
    # hypothetical deterministic resolver.
    placement: Placement | None = None
    slide_element_bounds: dict[str, Rect] | None = None
    # Doc 18 §4.3 — mirrored from the Diagram so the frontend knows whether
    # to start in build-up (hidden elements, reveal on focus) or overview
    # (all visible, dim non-focused). Optional for back-compat with older
    # manifests that didn't carry the field.
    presentation_mode: Literal["build_up", "overview"] | None = None


class TopicStartEvent(BaseModel):
    """Only used in chapter-level manifests so the runtime can track position."""

    type: Literal["topic_start"] = "topic_start"
    topic_id: str


# ---------------------------------------------------------------------------
# Notebook events — the teacher writing on the right-hand panel of SplitBoard.
# Zero playback duration; runtime appends a NotebookEntry and moves on so the
# entry appears AS THE VOICE SPEAKS the matching sentence.
# ---------------------------------------------------------------------------


class WriteSectionEvent(BaseModel):
    type: Literal["write_section"] = "write_section"
    id: str
    title: str
    placement: Placement | None = None


class WriteEquationEvent(BaseModel):
    type: Literal["write_equation"] = "write_equation"
    id: str
    latex: str
    align_group: str | None = Field(
        default=None,
        description="Equations sharing an align_group line up their '=' signs.",
    )
    boxed: bool = False
    placement: Placement | None = None


class WriteStepEvent(BaseModel):
    type: Literal["write_step"] = "write_step"
    id: str
    text: str
    indent: int = Field(default=0, ge=0, le=3)
    placement: Placement | None = None


class WriteTextEvent(BaseModel):
    type: Literal["write_text"] = "write_text"
    id: str
    text: str
    placement: Placement | None = None


class WriteKeyPointEvent(BaseModel):
    type: Literal["write_key_point"] = "write_key_point"
    id: str
    text: str
    placement: Placement | None = None


class WriteAnswerEvent(BaseModel):
    type: Literal["write_answer"] = "write_answer"
    id: str
    text: str
    placement: Placement | None = None


class StrikethroughEvent(BaseModel):
    type: Literal["strikethrough"] = "strikethrough"
    target_id: str


class NewPageEvent(BaseModel):
    """Pre-Phase-3 marker-driven page break. Still emitted when a fragment
    stream has no LayoutPlanner attached (e.g., standalone narrations).
    Phase 3+ chapter narration emits PageBreakEvent instead.
    """

    type: Literal["new_page"] = "new_page"
    carry_forward_ids: list[str] = Field(default_factory=list)


class PageBreakEvent(BaseModel):
    """Phase 3 deterministic page break — emitted by the LayoutPlanner when
    measured notebook overflow occurs, a new diagram requires a fresh page,
    or a writer `<<NEW_PAGE>>` marker is seen. The slide_action distinguishes
    whether the slide stays put, swaps to a new diagram, or releases to a
    soft placeholder during the page turn.
    """

    type: Literal["page_break"] = "page_break"
    new_page_index: int = Field(..., ge=0)
    slide_action: Literal["keep", "swap", "release"]
    next_diagram_id: str | None = None
    notebook_carry_forward_ids: list[str] = Field(default_factory=list)
    reason: Literal["text_overflow", "new_diagram", "writer_marker"]


# ---------------------------------------------------------------------------
# Attention-direction events (doc 18 spotlight redesign)
#
# Doc-18 primitive: spotlight one role on the active diagram.
#   FocusEvent     — spotlight `target_role`; optional inline label `text`.
#                    Replaces previous focus on the same diagram.
#   UnfocusEvent   — release the current focus (rarely emitted; next FOCUS
#                    or SHOW_DIAGRAM implicitly releases).
#   ClearAnnotationsEvent — reset spotlight state for the active diagram.
#                    Kept as the canonical event name for back-compat with
#                    stored manifests that used CLEAR_ANNOTATIONS; the
#                    chunker emits one from either marker.
#
# Legacy events (PinEvent / CalloutEvent / BracketEvent / HighlightEvent /
# PulseEvent) below are READ-ONLY back-compat — the writer never emits new
# ones (the walker drops legacy fragments). They exist so older extraction
# files load + the frontend handlers don't crash mid-transition.
#
# Every focus targets a role from the active diagram's `dictionary`
# (Phase 1). The frontend resolves role → element_id via live-DOM query at
# render time; `target_element_id` is a fallback hint from the composer.
# ---------------------------------------------------------------------------


class FocusEvent(BaseModel):
    """Spotlight a single element of the active diagram.

    Doc 19 §A-3: `target_element_id` is now the PREFERRED selector (stable id
    from the diagram's dictionary). `target_role` is kept for back-compat with
    extraction files generated before the switch — those files only carried
    the role string. New events always populate both fields; the walker
    resolves role → element_id from the active diagram.

    `at_least_one_target` makes either field acceptable in isolation so old
    JSON deserializes cleanly, but FocusEvent({}, diagram_id) without either
    selector is a programmer error.
    """

    type: Literal["focus"] = "focus"
    diagram_id: str
    target_element_id: str | None = None
    target_role: str | None = None
    text: str = Field(
        default="",
        description="Optional 2-3 word inline label rendered near the focused element.",
    )

    @model_validator(mode="after")
    def at_least_one_target(self) -> "FocusEvent":
        if not self.target_element_id and not self.target_role:
            raise ValueError(
                "FocusEvent must specify target_element_id (preferred) or "
                "target_role (deprecated back-compat alias)."
            )
        return self


class UnfocusEvent(BaseModel):
    type: Literal["unfocus"] = "unfocus"
    diagram_id: str


# --- New live-annotation primitives (doc 19 §12) ----------------------------
#
# These four primitives extend FOCUS into a fuller "live whiteboard" surface.
# Phase A only defines the event shapes + walker→event mapping; Phase B builds
# the matching frontend components. The §7 hand-build proof exercises them
# end-to-end before Phase C wires the planner to emit them automatically.
# ---------------------------------------------------------------------------


class TraceEvent(BaseModel):
    """Animate a stroke along the element's path — for trajectories / curves.

    Frontend renders the element's outline as an animated dash that draws
    from 0 → full length over `duration_ms`. Stays visible after completion.
    """

    type: Literal["trace"] = "trace"
    diagram_id: str
    element_id: str = Field(min_length=1)
    duration_ms: int = Field(default=1500, ge=0)


class MarkPointEvent(BaseModel):
    """Drop a small marker at a (x, y) in the diagram's viewBox space.

    Used for marking landing points, intersections, ad-hoc reference dots
    that aren't part of the diagram's element dictionary.
    """

    type: Literal["mark_point"] = "mark_point"
    diagram_id: str
    x: float
    y: float
    kind: Literal["dot", "cross", "star"] = "dot"
    label: str = ""


class PointAtEvent(BaseModel):
    """A finger / arrow pointing at an element from a specified side.

    Lighter-weight than FOCUS — does not dim the rest of the diagram. Used
    when the teacher wants to "tap" a previously-focused element without
    re-spotlighting it.
    """

    type: Literal["point_at"] = "point_at"
    diagram_id: str
    element_id: str = Field(min_length=1)
    from_side: Literal["top", "bottom", "left", "right"] = "left"


class WriteMarginEvent(BaseModel):
    """Hand-written-style note rendered in the margin next to an element.

    For tiny inline annotations — e.g. an arrow with "= mg" or "ground frame"
    written next to a curve. Less heavyweight than a full diagram element.
    """

    type: Literal["write_margin"] = "write_margin"
    diagram_id: str
    anchor_element_id: str = Field(min_length=1)
    side: Literal["top", "bottom", "left", "right"] = "right"
    text: str = Field(min_length=1)


# --- Legacy annotation events (read-only back-compat) ------------------------


class PinEvent(BaseModel):
    type: Literal["pin"] = "pin"
    diagram_id: str
    annotation_id: str
    target_role: str
    target_element_id: str | None = None
    text: str
    position: Literal["above", "below", "left", "right"] = "above"


class CalloutEvent(BaseModel):
    type: Literal["callout"] = "callout"
    diagram_id: str
    annotation_id: str
    target_role: str
    target_element_id: str | None = None
    text: str
    direction: Literal[
        "up", "down", "up-right", "up-left", "down-right", "down-left"
    ] = "up-right"


class BracketEvent(BaseModel):
    type: Literal["bracket"] = "bracket"
    diagram_id: str
    annotation_id: str
    target_role_a: str
    target_role_b: str
    target_element_id_a: str | None = None
    target_element_id_b: str | None = None
    label: str
    side: Literal["above", "below", "left", "right"] = "above"


class HighlightEvent(BaseModel):
    type: Literal["highlight"] = "highlight"
    diagram_id: str
    target_role: str
    target_element_id: str | None = None
    duration_ms: int = Field(default=1500, ge=0)
    color_token: str | None = None


class PulseEvent(BaseModel):
    type: Literal["pulse"] = "pulse"
    diagram_id: str
    target_role: str
    target_element_id: str | None = None
    duration_ms: int = Field(default=800, ge=0)
    color_token: str | None = None


class ClearAnnotationsEvent(BaseModel):
    type: Literal["clear_annotations"] = "clear_annotations"
    diagram_id: str


ManifestEvent = Annotated[
    Union[
        AudioEvent,
        PauseEvent,
        ShowDiagramEvent,
        TopicStartEvent,
        WriteSectionEvent,
        WriteEquationEvent,
        WriteStepEvent,
        WriteTextEvent,
        WriteKeyPointEvent,
        WriteAnswerEvent,
        StrikethroughEvent,
        NewPageEvent,
        PageBreakEvent,
        FocusEvent,
        UnfocusEvent,
        ClearAnnotationsEvent,
        TraceEvent,
        MarkPointEvent,
        PointAtEvent,
        WriteMarginEvent,
        # Legacy back-compat (writer no longer emits):
        PinEvent,
        CalloutEvent,
        BracketEvent,
        HighlightEvent,
        PulseEvent,
    ],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Per-page diagnostic summary (Phase 3) — attached to Chapter as `pages`.
# Not user-facing; used for post-hoc analysis of pagination quality.
# ---------------------------------------------------------------------------


class PageSummary(BaseModel):
    page_index: int = Field(..., ge=0)
    topic_id: str
    slide_diagram_id: str | None = None
    notebook_block_count: int = Field(default=0, ge=0)
    notebook_height_used_px: float = Field(default=0.0, ge=0.0)
    notebook_height_total_px: float = Field(default=0.0, ge=0.0)
    annotations_count: int = Field(default=0, ge=0)


# ---------------------------------------------------------------------------
# Unified board state (feat/unify_boardstate).
#
# Authoritative "what is on the board" at end-of-page. One BoardSnapshot per
# Chapter.pages entry at matching index. Built deterministically by the
# manifest composer from PageState (SlideState.element_bounds + NotebookState
# blocks); consumed by the live agent and the frontend so neither has to
# rebuild from event walks or query the DOM to know where things are.
# ---------------------------------------------------------------------------


class BoardElement(BaseModel):
    """One element placed on the board at a snapshot moment.

    `kind` discriminates how to interpret the optional fields:
      diagram          → element_id is the diagram_id; rect is its slide rect
      diagram_element  → element_id is the stable id from the diagram's
                         dictionary; parent_id is the diagram_id; role is the
                         role string; semantic is the dictionary's semantic term
      notebook_block   → element_id is the fragment_id; block_type is set
    """

    element_id: str
    kind: Literal["diagram", "diagram_element", "notebook_block"]
    rect: Rect
    parent_id: str = ""
    role: str = ""
    block_type: str = ""
    semantic: str = ""


class BoardSnapshot(BaseModel):
    page_index: int = Field(..., ge=0)
    topic_id: str = ""
    elements: list[BoardElement] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Concept-to-Visual Index (Idea 2).
#
# One row per (diagram, dictionary element). Built once at ingest from each
# Diagram.render_data.dictionary. Persisted on the Chapter so doubt
# resolution + future auto-FOCUS passes can do an O(N) substring scan
# without re-parsing every diagram's full render_data. Keyed by linked_beat_id
# so beat-anchored consumers (e.g., "what visuals are introduced in this
# beat?") can narrow scope.
# ---------------------------------------------------------------------------


class VisualTermEntry(BaseModel):
    """One indexable element on one diagram.

    The pair (diagram_id, element_id) is the stable handle; (role, semantic)
    are the searchable strings (lowercased at lookup time, not write time, to
    keep originals readable). `linked_beat_id` carries the parent diagram's
    beat anchor so beat-scoped lookups stay deterministic.
    """

    diagram_id: str
    element_id: str
    role: str = ""
    semantic: str = ""
    linked_beat_id: str = ""


class ConceptVisualIndex(BaseModel):
    """Flat list of VisualTermEntry — one per dictionary element across all
    diagrams in the chapter. Order is stable (diagram id, then element id)
    so the index is byte-identical across re-runs unless the diagrams change.
    """

    entries: list[VisualTermEntry] = Field(default_factory=list)


class Manifest(BaseModel):
    """Ordered event sequence for audio + diagram playback."""

    events: list[ManifestEvent] = Field(default_factory=list)

    @property
    def total_audio_ms(self) -> int:
        return sum(
            e.duration_ms
            for e in self.events
            if isinstance(e, (AudioEvent, PauseEvent))
        )


# ---------------------------------------------------------------------------
# BookSkeleton — global structure extracted once per book (carried from v1)
# ---------------------------------------------------------------------------


class ChapterSummary(BaseModel):
    chapter_index: int = Field(..., description="1-based position in book")
    title: str
    page_start: int
    page_end: int
    summary: str
    key_concepts: list[str] = Field(default_factory=list)
    prerequisites_from: list[str] = Field(default_factory=list)
    leads_to: list[str] = Field(default_factory=list)


class BookSkeleton(BaseModel):
    textbook_title: str
    subject: str
    total_chapters: int
    total_pages: int
    chapters: list[ChapterSummary] = Field(default_factory=list)
    subject_overview: str = ""

    def chapter_by_index(self, index: int) -> ChapterSummary | None:
        for ch in self.chapters:
            if ch.chapter_index == index:
                return ch
        return None

    def chapter_by_title(self, title: str) -> ChapterSummary | None:
        title_lower = title.lower()
        for ch in self.chapters:
            if title_lower in ch.title.lower() or ch.title.lower() in title_lower:
                return ch
        return None


# ---------------------------------------------------------------------------
# Diagram
# ---------------------------------------------------------------------------


class DiagramRenderer(str, Enum):
    SVG = "svg"
    MANIM = "manim"


class Diagram(BaseModel):
    diagram_id: str
    renderer: DiagramRenderer
    render_data: dict[str, Any] = Field(..., description="Renderer-specific spec")
    description: str
    fallback_image_url: str | None = Field(
        default=None,
        description="Pre-rendered PNG (svg) or MP4 (manim); set during media phase",
    )
    linked_topic_ids: list[str] = Field(default_factory=list)
    linked_beat_id: str = Field(
        default="",
        description=(
            "Phase 4c — populated for per-beat diagrams (format: '{topic_id}_b{beat_index}'); "
            "empty for legacy per-topic diagrams."
        ),
    )
    # Doc 18 §4.3 — how the frontend should reveal this diagram's elements.
    #   "build_up": elements start hidden; first FOCUS on each reveals it.
    #               Matches a teacher drawing as they talk. Default for
    #               concept-style beats (hook/big_picture/first_principles/
    #               visual_build/misconception).
    #   "overview": all elements visible from the start (slightly dimmed);
    #               FOCUS spotlights the active one. Matches a teacher
    #               pointing at a pre-drawn reference. Default for explain/
    #               derive/example and for Phase 1 per-topic diagrams.
    presentation_mode: Literal["build_up", "overview"] = "overview"
    needs_review: bool = False
    version: int = 1


# ---------------------------------------------------------------------------
# Question
# ---------------------------------------------------------------------------


class QuestionType(str, Enum):
    MCQ = "mcq"
    SOLVED_EXAMPLE = "solved_example"


class QuestionSource(str, Enum):
    BOOK = "book"
    GENERATED = "generated"


class Question(BaseModel):
    question_id: str
    q_text: str
    q_audio_url: str | None = None
    q_diagram_id: str | None = None
    answer: str
    answer_audio_url: str | None = None
    options: list[str] = Field(
        default_factory=list, description="Empty for solved_example"
    )
    type: QuestionType
    source: QuestionSource
    solution_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    linked_topic_ids: list[str] = Field(default_factory=list)
    needs_review: bool = False
    language: str = "en"
    version: int = 1


# ---------------------------------------------------------------------------
# Topic — the atomic teaching unit (one per anchored section)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Book examples — verbatim worked-out problems + quantitative inline
# illustrations pulled straight from the textbook. The product USP is that
# every book example becomes a beat in the lecture; the LLM never invents
# examples that masquerade as the book's. Extended (LLM) examples are a
# separate, additive concept — see allocator logic in lecture_plan.
# ---------------------------------------------------------------------------


class BookExample(BaseModel):
    """One worked-out problem or quantitative inline illustration from the book.

    The narration MUST preserve `setup_facts` (numbers + relationships) and
    the conclusion. Character names + surface phrasing CAN be localized. Pure
    analogies don't count — only quantitative content lives here.
    """

    verbatim_text: str = Field(
        ...,
        description="The example passage quoted from the textbook. Used as the "
        "source of truth — when the narration drifts, regenerate against this.",
    )
    page_number: int | None = None
    kind: Literal["worked_out", "inline"] = Field(
        ...,
        description="`worked_out` = numbered Example boxes with full solutions; "
        "`inline` = quantitative illustrations woven into the prose.",
    )
    lesson_focus: str = Field(
        ...,
        min_length=1,
        description="One sentence stating what the student should walk away "
        "understanding. The writer uses this to anchor the narration.",
    )
    setup_facts: list[str] = Field(
        default_factory=list,
        description="Numbers and relationships that MUST appear in the narration "
        "(e.g., 'mass = 2 kg', 'F = 10 N'). Faithfulness contract.",
    )
    has_derivation: bool = Field(
        default=False,
        description="When True, the writer renders step-by-step via "
        "<<WRITE_STEP>> markers instead of compressing to one beat.",
    )


class Topic(BaseModel):
    # identity
    topic_id: str
    chapter_id: str
    section_number: str = Field(..., description="e.g. '12.1.1' — anchored from PDF")
    within_chapter_order: int
    topic_name: str

    # source content
    orig_book_content: str = Field(..., description="Verbatim from PDF")
    our_understanding: str = Field(..., description="LLM teacher-voice explanation")
    examples: list[str] = Field(
        default_factory=list,
        description="Legacy mixed-source examples (back-compat). New extractions "
        "populate `book_examples` separately and leave this empty.",
    )

    # USP: book coverage + LLM extension
    book_examples: list[BookExample] = Field(
        default_factory=list,
        description="Examples quoted from the textbook. Every entry MUST become "
        "a faithful beat in the lecture (allocator + writer contract).",
    )

    # graph navigation
    next_topic_id: str | None = None
    prereq_topic_ids: list[str] = Field(default_factory=list)
    has_diagram_ids: list[str] = Field(default_factory=list)
    has_question_ids: list[str] = Field(default_factory=list)

    # playback
    standalone_manifest: Manifest = Field(default_factory=Manifest)
    # Raw script (with inline <<SECTION>>/<<WRITE_*>>/<<SHOW_DIAGRAM>>/<<PAUSE>>
    # markers) used to produce the standalone_manifest. Persisted so the
    # narration is recoverable, re-TTS-able, and inspectable.
    standalone_narration_text: str = ""

    # retrieval + QA
    embedding: list[float] = Field(default_factory=list)
    needs_review: bool = False
    language: str = "en"
    version: int = 1

    @property
    def complexity_score(self) -> int:
        """Deterministic difficulty signal: number of explicit prerequisites.

        Replaces the dropped `difficulty_level` LLM rating with something
        repeatable. Higher score → more extended examples allocated.
        """
        return len(self.prereq_topic_ids)

    def n_extended_examples(self) -> int:
        """How many LLM-generated extra examples to add for this topic.

        The product rule (locked with user 2026-05-27):
          - Empty book examples + ≥3 prereqs → 2 extras (the 'we win' case:
            book skipped a hard topic, we make up for it).
          - Empty book examples + <3 prereqs → 0 extras (respect book intent).
          - Has book examples + 0 prereqs        → 1 extra.
          - Has book examples + 1-2 prereqs      → 2 extras.
          - Has book examples + ≥3 prereqs       → 3 extras.
        """
        if not self.book_examples:
            return 2 if self.complexity_score >= 3 else 0
        if self.complexity_score == 0:
            return 1
        if self.complexity_score <= 2:
            return 2
        return 3


# ---------------------------------------------------------------------------
# Chapter
# ---------------------------------------------------------------------------


class Chapter(BaseModel):
    chapter_id: str
    chapter_index: int
    title: str
    summary: str
    page_start: int
    page_end: int
    topic_ids: list[str] = Field(
        default_factory=list, description="Ordered by lecture flow"
    )
    chapter_manifest: Manifest = Field(default_factory=Manifest)
    # Full chapter-context narration (with inline markers) the LLM produced.
    narration_text: str = ""
    # Phase 3: per-page diagnostic summary. Populated by ManifestComposer
    # when LayoutPlanner is active. Empty for chapters generated pre-Phase-3
    # or via fragment streams without layout. Used for pagination quality
    # analysis (notebook fill %, page count distribution, etc).
    pages: list[PageSummary] = Field(default_factory=list)
    # Unified board state (feat/unify_boardstate). One BoardSnapshot per
    # `pages` entry at matching index — authoritative slide + notebook layout
    # at end-of-page. Read by the live agent and the frontend instead of
    # rebuilding from events or DOM. Empty for pre-feature extractions.
    board_snapshots: list[BoardSnapshot] = Field(default_factory=list)
    # Idea 2: Concept-to-Visual Index. Flat lookup over every dictionary
    # element on every diagram in this chapter. The doubt resolver pulls
    # entries for the active diagram into its prompt; downstream auto-FOCUS
    # consumers scan `semantic` for narration-mentioned terms.
    concept_visual_index: ConceptVisualIndex = Field(default_factory=ConceptVisualIndex)
    # Phase 4b: chapter-level lecture plan (ChapterLecturePlanner output) +
    # per-topic teaching plans (ConceptPlanner output via kernel). Sidecar
    # artifacts — pre-Phase-4c stages don't consume them. Optional so older
    # extractions (pre-4b) load without migration.
    lecture_plan: "ChapterLecturePlan | None" = None
    concept_plans: "list[ConceptTeachingPlan]" = Field(default_factory=list)
    # Phase 4d: per-beat narrations produced by BeatNarrationWriter, trimmed
    # to budget by LengthEnforcer. Phase 4e: feeds ScriptAssembler.
    beat_narrations: "list[BeatNarration]" = Field(default_factory=list)
    # Phase 4d: ScriptAssembler output (dict-form of ChapterScript dataclass —
    # {chapter_id, segments: [{topic_id, narration_chapter, narration_standalone}]}).
    # Stored as dict so Pydantic can serialize without coupling to the
    # lecture_script dataclass. Pipeline Phase 8 reconstructs the dataclass.
    assembled_chapter_script: dict[str, Any] | None = None
    # Phase H (doc 19) — per-topic LessonPlan + prosody-applied TopicNarration
    # produced by LessonQualityGate + LessonProsody. Empty when
    # cfg.enrichment.use_lesson_pipeline=False (legacy path). When populated,
    # supersedes the legacy concept_plans + beat_narrations as the source of
    # `assembled_chapter_script`.
    lesson_plans: "list[LessonPlan]" = Field(default_factory=list)
    lesson_narrations: "list[TopicNarration]" = Field(default_factory=list)
    embedding: list[float] = Field(default_factory=list)
    language: str = "en"
    version: int = 1


# ---------------------------------------------------------------------------
# Extraction result — pipeline's intermediate container
# ---------------------------------------------------------------------------


class ExtractionSource(BaseModel):
    textbook_title: str
    extractor_model: str
    extraction_timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat()
    )


class CurriculumExtractionResult(BaseModel):
    """Full result of one pipeline run, inspectable as JSON before ingestion."""

    version: str = "2.0"
    subject: str
    textbook_title: str
    source: ExtractionSource
    book_skeleton: BookSkeleton | None = None
    chapters: list[Chapter] = Field(default_factory=list)
    topics: list[Topic] = Field(default_factory=list)
    diagrams: list[Diagram] = Field(default_factory=list)
    questions: list[Question] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def topic_ids(self) -> set[str]:
        return {t.topic_id for t in self.topics}

    def topic_by_id(self, topic_id: str) -> Topic | None:
        for t in self.topics:
            if t.topic_id == topic_id:
                return t
        return None

    def counts(self) -> dict[str, int]:
        return {
            "chapters": len(self.chapters),
            "topics": len(self.topics),
            "diagrams": len(self.diagrams),
            "questions": len(self.questions),
        }

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> CurriculumExtractionResult:
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


# Resolve Phase 4b + 4d forward references on Chapter (lecture_plan,
# concept_plans, beat_narrations). Imported at the bottom because the
# referenced modules import from this module transitively, so eager top-level
# imports would create a cycle. With `from __future__ import annotations`
# above, the field annotations are stringified until model_rebuild() resolves
# them here.
from feynman_teaching_kernel import ConceptTeachingPlan  # noqa: E402

from lecture_pipeline_v2.curriculum.beat_narration.models import BeatNarration  # noqa: E402
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_narrator import (  # noqa: E402
    TopicNarration,
)
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_plan_models import (  # noqa: E402
    LessonPlan,
)
from lecture_pipeline_v2.curriculum.lecture_plan.models import ChapterLecturePlan  # noqa: E402

Chapter.model_rebuild()
CurriculumExtractionResult.model_rebuild()
