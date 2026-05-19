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
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field


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


class TopicStartEvent(BaseModel):
    """Only used in chapter-level manifests so the runtime can track position."""

    type: Literal["topic_start"] = "topic_start"
    topic_id: str


ManifestEvent = Annotated[
    Union[AudioEvent, PauseEvent, ShowDiagramEvent, TopicStartEvent],
    Field(discriminator="type"),
]


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
    options: list[str] = Field(default_factory=list, description="Empty for solved_example")
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
    examples: list[str] = Field(default_factory=list)

    # graph navigation
    next_topic_id: str | None = None
    prereq_topic_ids: list[str] = Field(default_factory=list)
    has_diagram_ids: list[str] = Field(default_factory=list)
    has_question_ids: list[str] = Field(default_factory=list)

    # playback
    standalone_manifest: Manifest = Field(default_factory=Manifest)

    # retrieval + QA
    embedding: list[float] = Field(default_factory=list)
    needs_review: bool = False
    language: str = "en"
    version: int = 1


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
    topic_ids: list[str] = Field(default_factory=list, description="Ordered by lecture flow")
    chapter_manifest: Manifest = Field(default_factory=Manifest)
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
