"""ULQF data models — doc 20 Unified Lecture Quality Framework."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class QualityDimension(str, Enum):
    """Top-level quality hierarchy from ULQF."""

    provenance = "provenance"
    curriculum_extraction = "curriculum_extraction"
    chapter_arc = "chapter_arc"
    lesson_plan = "lesson_plan"
    narration = "narration"
    layout = "layout"
    educational = "educational"
    assessment = "assessment"
    composite = "composite"


class MetricDefinition(BaseModel):
    """Catalog entry for one ULQF metric."""

    metric_id: str
    name: str
    dimension: QualityDimension
    description: str
    unit: str | None = None
    higher_is_better: bool = True


class MetricValue(BaseModel):
    """One measured value at run, chapter, or topic granularity."""

    metric_id: str
    name: str
    dimension: QualityDimension
    value: float | int | str | bool | None
    unit: str | None = None
    level: str = Field(default="run", description="run | chapter | topic")
    chapter_id: str | None = None
    topic_id: str | None = None
    # normalized 0–100 for index composition; None when not applicable
    score_0_100: float | None = None


class RunMetadata(BaseModel):
    """Optional pipeline run context not stored in extraction.json."""

    label: str = ""
    persona_id: str | None = None
    pipeline_version: str = "lecture-pipeline-v2"
    total_elapsed_seconds: float | None = None
    skipped_phases: list[str] = Field(default_factory=list)
    config_hash: str | None = None
    source_path: str | None = None


class QualityIndices(BaseModel):
    """Composite scores — ULQF hierarchy."""

    technical_quality_index: float | None = Field(
        None, description="TQI — structural + extraction integrity"
    )
    educational_quality_index: float | None = Field(
        None, description="EQI — pedagogical structure proxies"
    )
    learning_effectiveness_index: float | None = Field(
        None, description="LEI — coverage + lesson completeness"
    )
    lecture_excellence_score: float | None = Field(
        None, description="LES — weighted composite (no runtime RLI yet)"
    )


class QualityReport(BaseModel):
    """Full metric snapshot for one extraction / pipeline run."""

    framework_version: str = "1.0"
    ulqf_reference: str = "doc-20"
    evaluated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    subject: str
    textbook_title: str
    run: RunMetadata = Field(default_factory=RunMetadata)
    metrics: list[MetricValue] = Field(default_factory=list)
    indices: QualityIndices = Field(default_factory=QualityIndices)
    gates: list["QualityGateResult"] = Field(default_factory=list)

    def metric(self, metric_id: str) -> MetricValue | None:
        for m in self.metrics:
            if m.metric_id == metric_id and m.level == "run":
                return m
        return None

    def save(self, path: str) -> None:
        from pathlib import Path

        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str) -> QualityReport:
        from pathlib import Path

        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


class MetricDelta(BaseModel):
    metric_id: str
    name: str
    dimension: QualityDimension
    baseline: Any
    candidate: Any
    delta: float | None = None
    improved: bool | None = None


class QualityComparison(BaseModel):
    """Side-by-side diff of two QualityReports."""

    baseline_label: str
    candidate_label: str
    compared_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    index_deltas: dict[str, float] = Field(default_factory=dict)
    metric_deltas: list[MetricDelta] = Field(default_factory=list)

    def save(self, path: str) -> None:
        from pathlib import Path

        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.model_dump_json(indent=2), encoding="utf-8")
