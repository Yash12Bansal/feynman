"""Persisted quality artifacts — written at ingest, read by QEE."""

from __future__ import annotations

from pydantic import BaseModel, Field

from lecture_pipeline_v2.curriculum.lecture_plan.lesson_judge import PlanJudgement


class DiagramJudgementRecord(BaseModel):
    diagram_id: str
    score: int = Field(ge=1, le=5)
    passed: bool = True
    issue: str = ""


class TopicGateRecord(BaseModel):
    topic_id: str
    plan_judgement: PlanJudgement | None = None
    plan_regen_attempts: int = 0
    diagram_judgements: list[DiagramJudgementRecord] = Field(default_factory=list)
    needs_review: bool = False


class ValidationGateSnapshot(BaseModel):
    structural_errors: int = 0
    structural_warnings: int = 0
    semantic_topics_checked: int = 0
    semantic_topics_flagged: int = 0
    semantic_wrong_count: int = 0
    semantic_drift_count: int = 0
    diagram_render_checked: int = 0
    diagram_render_failed: int = 0


class ChapterQualitySnapshot(BaseModel):
    chapter_id: str
    topic_gates: list[TopicGateRecord] = Field(default_factory=list)
    book_coverage_pct: float | None = None
    book_coverage_gaps: int = 0
    lesson_gate_passed: int = 0
    lesson_gate_seen: int = 0


class NarrationJudgementRecord(BaseModel):
    topic_id: str
    domain_fit_score: int = Field(ge=0, le=100, default=50)
    analogy_leakage_score: int = Field(
        ge=0, le=100, default=0, description="0 = no leakage, 100 = heavy wrong-domain"
    )
    clarity_score: int = Field(ge=0, le=100, default=50)
    engagement_score: int = Field(ge=0, le=100, default=50)
    factual_grounding_score: int = Field(ge=0, le=100, default=50)
    skipped: bool = False
    issue: str = ""


class QualitySnapshot(BaseModel):
    """Root quality artifact on CurriculumExtractionResult."""

    version: str = "1.0"
    persona_id: str | None = None
    validation: ValidationGateSnapshot | None = None
    chapters: list[ChapterQualitySnapshot] = Field(default_factory=list)
    narration_judgements: list[NarrationJudgementRecord] = Field(default_factory=list)

    def chapter(self, chapter_id: str) -> ChapterQualitySnapshot | None:
        for ch in self.chapters:
            if ch.chapter_id == chapter_id:
                return ch
        return None
