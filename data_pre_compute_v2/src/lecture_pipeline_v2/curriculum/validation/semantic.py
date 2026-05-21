"""Semantic spot-check — LLM compares our_understanding against orig_book_content.

Samples a fraction of topics; flags any whose explanation drifts factually
from the source. Flagged topics get needs_review=True; pipeline continues.
"""

from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass, field

from ...llm.base import LLMProvider
from ..models import CurriculumExtractionResult, Topic
from .models import ValidationIssue, ValidationReport

logger = logging.getLogger(__name__)


SEMANTIC_SYSTEM_PROMPT = """You are a factual validator for educational content.

You will be given a passage of text from a textbook and a teacher's plain-language explanation of that passage. Decide whether the explanation is factually consistent with the source.

Return a JSON object with these keys:
- verdict: "consistent" or "drift" or "wrong"
- issues: array of one-sentence descriptions of any factual problems (empty array if all good)

"consistent" = the explanation is faithful to the source.
"drift" = the explanation misses or simplifies something, but isn't factually wrong.
"wrong" = the explanation contradicts the source or adds incorrect facts.

Return ONLY the JSON. No markdown. No commentary."""


@dataclass
class SemanticValidationReport:
    topics_checked: int = 0
    topics_flagged: int = 0
    elapsed_seconds: float = 0.0
    issues: list[ValidationIssue] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"Semantic validation — {self.topics_checked} topics checked, "
            f"{self.topics_flagged} flagged for review, "
            f"{self.elapsed_seconds:.1f}s"
        )


class SemanticValidator:
    def __init__(self, llm: LLMProvider, *, sample_rate: float = 0.20, seed: int | None = None):
        self.llm = llm
        self.sample_rate = sample_rate
        self._rng = random.Random(seed)

    def validate(self, extraction: CurriculumExtractionResult) -> SemanticValidationReport:
        report = SemanticValidationReport()
        start = time.monotonic()

        sample = self._select_sample(extraction.topics)
        report.topics_checked = len(sample)

        for topic in sample:
            try:
                self._check_topic(topic, report)
            except Exception as e:
                logger.warning("Semantic check failed for %s: %s", topic.topic_id, e)

        report.elapsed_seconds = time.monotonic() - start
        logger.info(report.summary())
        return report

    def _select_sample(self, topics: list[Topic]) -> list[Topic]:
        if not topics or self.sample_rate <= 0:
            return []
        k = max(1, int(len(topics) * self.sample_rate))
        k = min(k, len(topics))
        return self._rng.sample(topics, k)

    def _check_topic(self, topic: Topic, report: SemanticValidationReport) -> None:
        user_prompt = (
            f"## Source text (verbatim from textbook)\n\n{topic.orig_book_content[:4000]}\n\n"
            f"## Teacher's explanation\n\n{topic.our_understanding}\n\n"
            f"Validate the explanation against the source."
        )
        response = self.llm.generate_json(SEMANTIC_SYSTEM_PROMPT, user_prompt)
        try:
            data = json.loads(response.content)
        except json.JSONDecodeError:
            return

        verdict = (data.get("verdict") or "").strip().lower()
        issues = data.get("issues") or []

        if verdict in ("drift", "wrong"):
            severity = "error" if verdict == "wrong" else "warning"
            level = "warning"  # all semantic issues flag, none block
            for issue_msg in (issues or [verdict]):
                report.issues.append(ValidationIssue(
                    level=level, code=f"SEMANTIC_{verdict.upper()}",
                    message=str(issue_msg), entity_id=topic.topic_id,
                ))
            topic.needs_review = True
            report.topics_flagged += 1
