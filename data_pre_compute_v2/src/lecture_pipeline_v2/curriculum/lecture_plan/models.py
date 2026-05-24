"""Chapter-level lecture plan: the arc for a whole chapter (5–15 topics)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CoverageChecklistItem(BaseModel):
    description: str = Field(..., description="What this chapter must teach/show")
    owned_by_topic_id: str | None = Field(
        None,
        description="Topic ID that primarily covers this item (None = unassigned)",
    )


class ChapterLecturePlan(BaseModel):
    """Chapter-wide planning artifact produced by ChapterLecturePlanner.

    Cross-document constraint: concept_sequence is a subset (or permutation)
    of the chapter's topic_ids. Enforced at construction time by the planner,
    not by Pydantic.
    """

    chapter_id: str
    chapter_title: str
    chapter_arc: str = Field(
        ...,
        description="2–3 sentence narrative spine for the entire chapter",
    )
    opening_hook: str = Field(
        ...,
        description="Chapter-level hook — distinct from per-concept hooks; the lead-in for the whole lecture",
    )
    concept_sequence: list[str] = Field(
        ...,
        description="Ordered topic_ids in teaching order — drives ConceptPlanner",
    )
    coverage_checklist: list[CoverageChecklistItem] = Field(
        default_factory=list,
        description="Items the chapter must cover; can be assigned to specific topics",
    )
    length_budget_seconds: int = Field(
        ...,
        gt=0,
        description="Total teaching budget for the chapter (e.g., 5–15 minutes for IGCSE)",
    )
    per_concept_budget_seconds: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "topic_id → seconds. Sum should approximately equal length_budget_seconds."
        ),
    )
    closing_summary: str = Field(
        ...,
        description="Single-paragraph resolution for the chapter — what the student should leave with",
    )
