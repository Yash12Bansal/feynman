"""Evaluation context — extraction + optional pipeline run metadata."""

from __future__ import annotations

from dataclasses import dataclass, field

from lecture_pipeline_v2.curriculum.models import CurriculumExtractionResult

from .models import RunMetadata


@dataclass
class EvaluationContext:
    extraction: CurriculumExtractionResult
    run: RunMetadata = field(default_factory=RunMetadata)
    narration_judgements: list = field(default_factory=list)

    @property
    def topics(self):
        return self.extraction.topics

    @property
    def chapters(self):
        return self.extraction.chapters

    @property
    def topic_ids(self) -> set[str]:
        return self.extraction.topic_ids

    @property
    def quality_snapshot(self):
        return self.extraction.quality_snapshot
