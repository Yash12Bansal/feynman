"""Canonical models for the curriculum graph pipeline.

Defines the intermediate format between extraction and Neo4j ingestion.
Every extraction — whether from a single chapter, a chunk, or the full book —
produces a CurriculumExtractionResult using these types.

Adapted from PMG's ExtractionResult pattern: decouple extraction from storage.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ConceptType(str, Enum):
    """Every concept node has exactly one type. The teaching agent uses this
    to decide teaching strategy — a FORMULA gets KaTeX, a MISCONCEPTION gets
    addressed proactively, a DERIVATION gets stepped through."""

    TOPIC = "topic"
    DEFINITION = "definition"
    FORMULA = "formula"
    DERIVATION = "derivation"
    EXAMPLE = "example"
    APPLICATION = "application"
    MISCONCEPTION = "misconception"
    ANALOGY = "analogy"
    EXPERIMENT = "experiment"
    VISUALIZATION = "visualization"


class ResolutionLevel(str, Enum):
    """Explicit zoom level for fractal navigation. The teaching agent zooms in
    when a student is confused, zooms out for recaps."""

    SYLLABUS = "syllabus"
    UNIT = "unit"
    CHAPTER = "chapter"
    CONCEPT = "concept"
    DETAIL = "detail"


class CurriculumRelationType(str, Enum):
    """All valid relationship types in the curriculum graph.
    The LLM prompt constrains output to only these types."""

    # Structural (hierarchy)
    CONTAINS = "contains"
    SUMMARIZES = "summarizes"

    # Pedagogical
    PREREQUISITE = "prerequisite"
    LEADS_TO = "leads_to"
    EXAMPLE_OF = "example_of"
    DERIVED_FROM = "derived_from"
    MISCONCEPTION_OF = "misconception_of"
    ANALOGY_FOR = "analogy_for"
    APPLICATION_OF = "application_of"

    # Cross-chapter
    CROSS_REFERENCES = "cross_references"
    SHARED_FOUNDATION = "shared_foundation"

    # Visual
    HAS_VISUAL = "has_visual"

    # Runtime evolution (populated by teaching agent, not pre-compute)
    CO_ACTIVATED_WITH = "co_activated_with"
    COMMONLY_CONFUSED = "commonly_confused"


class Difficulty(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


# ---------------------------------------------------------------------------
# BookSkeleton — global structure extracted once for the entire book
# ---------------------------------------------------------------------------


class ChapterSummary(BaseModel):
    """A chapter's role within the book. Extracted in Stage 3 (single LLM call)."""

    chapter_index: int = Field(..., description="1-based position in book")
    title: str
    page_start: int
    page_end: int
    summary: str = Field(..., description="2-3 sentence overview")
    key_concepts: list[str] = Field(
        default_factory=list, description="Major topics covered"
    )
    prerequisites_from: list[str] = Field(
        default_factory=list, description="Chapter titles this depends on"
    )
    leads_to: list[str] = Field(
        default_factory=list, description="Chapter titles that depend on this"
    )


class UnitGrouping(BaseModel):
    """A cluster of related chapters."""

    unit_name: str = Field(..., description="e.g. 'Oscillations & Waves'")
    chapter_indices: list[int] = Field(..., description="Which chapters belong (1-based)")
    theme: str = Field(..., description="Unifying theme description")


class CrossChapterPrerequisite(BaseModel):
    """An explicit prerequisite between two chapters."""

    from_chapter: str
    to_chapter: str
    reason: str


class BookSkeleton(BaseModel):
    """Global structure of the entire textbook. Extracted once (Stage 3)
    and passed as context to every chapter extraction."""

    textbook_title: str
    subject: str
    total_chapters: int
    total_pages: int
    chapters: list[ChapterSummary] = Field(
        ..., description="Ordered by book sequence"
    )
    units: list[UnitGrouping] = Field(
        default_factory=list, description="Chapter clusters"
    )
    cross_chapter_prerequisites: list[CrossChapterPrerequisite] = Field(
        default_factory=list
    )
    subject_overview: str = Field(
        ..., description="What this book covers overall"
    )

    def chapter_by_index(self, index: int) -> ChapterSummary | None:
        """Look up a chapter by its 1-based index."""
        for ch in self.chapters:
            if ch.chapter_index == index:
                return ch
        return None

    def chapter_by_title(self, title: str) -> ChapterSummary | None:
        """Fuzzy-ish lookup by title (case-insensitive containment)."""
        title_lower = title.lower()
        for ch in self.chapters:
            if title_lower in ch.title.lower() or ch.title.lower() in title_lower:
                return ch
        return None


# ---------------------------------------------------------------------------
# Extraction result — the canonical intermediate format
# ---------------------------------------------------------------------------


class ExtractionNode(BaseModel):
    """A concept extracted from curriculum content.
    Maps directly to a Neo4j node after ingestion."""

    # Identity
    uid: str = Field(..., description="Stable semantic ID (curriculum:subject:chapter:concept)")

    # Content
    topic_name: str
    concept_type: ConceptType
    resolution_level: ResolutionLevel
    section_number: str | None = Field(
        default=None,
        description="Textbook section ref: '12.1.3'. The extraction floor — "
        "every numbered section MUST have at least one node.",
    )
    summary: str = Field(..., description="LLM-generated exhaustive teaching summary")
    source_text: str = Field(default="", description="Verbatim from PDF")

    # Location
    page_start: int
    page_end: int
    chapter_order: int = Field(..., description="Which chapter in the book (1-based)")
    within_chapter_order: int = Field(
        ..., description="Concept sequence within the chapter"
    )
    global_teaching_order: int = Field(
        default=0,
        description="Computed: chapter_order * 1000 + within_chapter_order",
    )

    # Teaching metadata
    difficulty: Difficulty = Difficulty.INTERMEDIATE
    estimated_duration_minutes: float = Field(
        default=3.0, description="LLM-estimated time to teach this concept"
    )

    # Board intelligence bridge
    visual_hint: str | None = Field(
        default=None,
        description="What to draw on the board for this concept. "
        "e.g. 'Spring-mass energy diagram with KE/PE curves'",
    )

    # Hierarchy
    parent_uid: str | None = None
    children_uids: list[str] = Field(default_factory=list)

    # Extensible
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _compute_global_order(self) -> ExtractionNode:
        if self.global_teaching_order == 0:
            self.global_teaching_order = (
                self.chapter_order * 1000 + self.within_chapter_order
            )
        return self


class ExtractionRelationship(BaseModel):
    """A relationship between two concepts."""

    relationship_key: str = Field(..., description="Unique key for dedup")
    type: CurriculumRelationType
    from_uid: str
    to_uid: str
    label: str = Field(default="", description="Human-readable explanation")
    properties: dict[str, Any] = Field(default_factory=dict)


class ExtractionSource(BaseModel):
    """Provenance metadata for an extraction."""

    textbook_title: str
    chapter_title: str
    page_range: str = Field(..., description="e.g. '245-260'")
    extractor_model: str = Field(..., description="e.g. 'claude-sonnet-4'")
    extraction_timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat()
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class CurriculumExtractionResult(BaseModel):
    """Canonical intermediate format — the bridge between extraction and Neo4j.

    At chapter level: contains one chapter's concepts.
    At book level (after unification): contains ALL chapters' concepts merged.

    This format is:
    - Inspectable — serialize to JSON, review before committing to Neo4j
    - Mergeable — two extractions can be merged with entity resolution
    - Validatable — structural and semantic checks run on this before ingestion
    """

    version: str = "1.0"
    subject: str
    textbook_title: str
    scope: str = Field(
        default="chapter",
        description="'chapter' or 'book' (after unification)",
    )
    chapter_title: str | None = Field(
        default=None, description="None when scope='book'"
    )
    source: ExtractionSource
    book_skeleton: BookSkeleton | None = Field(
        default=None, description="Attached after Stage 3"
    )

    nodes: list[ExtractionNode]
    relationships: list[ExtractionRelationship]
    warnings: list[str] = Field(default_factory=list)

    # -- convenience accessors --

    @property
    def node_uids(self) -> set[str]:
        """All node UIDs in this extraction."""
        return {n.uid for n in self.nodes}

    def node_by_uid(self, uid: str) -> ExtractionNode | None:
        for n in self.nodes:
            if n.uid == uid:
                return n
        return None

    def nodes_by_type(self, concept_type: ConceptType) -> list[ExtractionNode]:
        return [n for n in self.nodes if n.concept_type == concept_type]

    def nodes_by_resolution(self, level: ResolutionLevel) -> list[ExtractionNode]:
        return [n for n in self.nodes if n.resolution_level == level]

    def relationships_by_type(
        self, rel_type: CurriculumRelationType
    ) -> list[ExtractionRelationship]:
        return [r for r in self.relationships if r.type == rel_type]

    def compute_counts(self) -> dict[str, dict[str, int]]:
        """Return node and relationship counts by type."""
        node_counts: dict[str, int] = {}
        for n in self.nodes:
            key = n.concept_type.value
            node_counts[key] = node_counts.get(key, 0) + 1

        rel_counts: dict[str, int] = {}
        for r in self.relationships:
            key = r.type.value
            rel_counts[key] = rel_counts.get(key, 0) + 1

        return {"nodes": node_counts, "relationships": rel_counts}

    def to_json(self, indent: int = 2) -> str:
        return self.model_dump_json(indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> CurriculumExtractionResult:
        return cls.model_validate_json(json_str)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json())

    @classmethod
    def load(cls, path: str | Path) -> CurriculumExtractionResult:
        return cls.from_json(Path(path).read_text())
