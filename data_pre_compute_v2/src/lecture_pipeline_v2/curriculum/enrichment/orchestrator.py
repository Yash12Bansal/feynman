"""Enrichment orchestrator — runs diagram + question jobs in parallel per topic.

After diagrams and questions exist, the orchestrator also wires the
has_diagram_ids / has_question_ids back onto each Topic.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from ...config import ValidationConfig
from ...llm.base import LLMProvider
from ..models import Diagram, Question, Topic
from .diagrams import DiagramGenerationReport, DiagramGenerator
from .questions import QuestionGenerationReport, QuestionGenerator

logger = logging.getLogger(__name__)


@dataclass
class EnrichmentReport:
    diagrams: DiagramGenerationReport
    questions: QuestionGenerationReport
    elapsed_seconds: float = 0.0

    def summary(self) -> str:
        return (
            f"Enrichment complete in {self.elapsed_seconds:.1f}s\n"
            f"    {self.diagrams.summary()}\n"
            f"    {self.questions.summary()}"
        )


class EnrichmentOrchestrator:
    def __init__(
        self,
        author_llm: LLMProvider,
        validation_config: ValidationConfig,
        *,
        diagram_concurrency: int = 5,
        question_concurrency: int = 5,
    ):
        self.diagram_gen = DiagramGenerator(author_llm, concurrency=diagram_concurrency)
        self.question_gen = QuestionGenerator(
            author_llm,
            validation_config.judge_models,
            concurrency=question_concurrency,
            agreement_threshold=validation_config.judge_agreement_threshold,
        )

    async def enrich(
        self,
        topics: list[Topic],
        existing_diagram_ids: set[str] | None = None,
        existing_question_ids: set[str] | None = None,
        *,
        skip_diagrams: bool = False,
    ) -> tuple[list[Diagram], list[Question], EnrichmentReport]:
        """Run per-topic enrichment (diagrams + questions).

        `skip_diagrams=True` bypasses the legacy `DiagramGenerator` entirely
        and returns an empty diagrams list. Used by doc-19 (Phase H) where
        `LessonDiagramGenerator` owns diagram production downstream and the
        legacy enrichment would just pollute `extraction.diagrams` with
        dead per-topic diagrams that no manifest event references.
        """
        start = time.monotonic()

        questions_task = self.question_gen.generate_for_topics(
            topics, existing_question_ids
        )

        if skip_diagrams:
            diagrams: list[Diagram] = []
            diag_report = DiagramGenerationReport()
            questions, q_report = await questions_task
        else:
            diagrams_task = self.diagram_gen.generate_for_topics(
                topics, existing_diagram_ids
            )
            (diagrams, diag_report), (questions, q_report) = await asyncio.gather(
                diagrams_task,
                questions_task,
            )

        self._wire_topic_refs(topics, diagrams, questions)

        elapsed = time.monotonic() - start
        report = EnrichmentReport(
            diagrams=diag_report,
            questions=q_report,
            elapsed_seconds=elapsed,
        )
        logger.info(report.summary())
        return diagrams, questions, report

    @staticmethod
    def _wire_topic_refs(
        topics: list[Topic], diagrams: list[Diagram], questions: list[Question]
    ) -> None:
        topic_by_id = {t.topic_id: t for t in topics}
        for d in diagrams:
            for tid in d.linked_topic_ids:
                topic = topic_by_id.get(tid)
                if topic and d.diagram_id not in topic.has_diagram_ids:
                    topic.has_diagram_ids.append(d.diagram_id)
        for q in questions:
            for tid in q.linked_topic_ids:
                topic = topic_by_id.get(tid)
                if topic and q.question_id not in topic.has_question_ids:
                    topic.has_question_ids.append(q.question_id)
