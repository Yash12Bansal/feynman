"""Book-example coverage validator (Idea 2 + USP).

For every Topic.book_examples entry, there MUST be at least one BeatNarration
with example_source="book" and book_example_ref pointing back to it. This
guarantees the product promise that the lecture covers every book example.

v1: soft-warn — emit structured logs for gaps, return a CoverageReport. The
pipeline doesn't fail. After we've seen a few real ingest runs and gauged
how often the LLM/allocator drifts, promote to hard fail.

Pure function. No IO. Easy to unit-test.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..beat_narration.models import BeatNarration
from ..models import Topic

logger = logging.getLogger(__name__)


@dataclass
class CoverageGap:
    topic_id: str
    section_number: str
    book_example_ref: int
    lesson_focus: str


@dataclass
class CoverageReport:
    topics_checked: int = 0
    book_examples_total: int = 0
    book_examples_covered: int = 0
    extended_beats_emitted: int = 0
    gaps: list[CoverageGap] = field(default_factory=list)

    @property
    def coverage_pct(self) -> float:
        if self.book_examples_total == 0:
            return 1.0
        return self.book_examples_covered / self.book_examples_total

    def summary(self) -> str:
        return (
            f"book-example coverage: "
            f"{self.book_examples_covered}/{self.book_examples_total} "
            f"({self.coverage_pct:.0%}); extended beats emitted: "
            f"{self.extended_beats_emitted}; gaps: {len(self.gaps)}"
        )


def validate_example_coverage(
    topics: list[Topic],
    narrations_by_topic: dict[str, list[BeatNarration]],
) -> CoverageReport:
    """Check every Topic.book_examples is covered by at least one narration.

    `narrations_by_topic[topic_id]` is the list of BeatNarrations produced
    for that topic. Topics without book_examples are skipped (nothing to
    validate). Empty narration text is treated as 'beat exists but failed
    to render' — coverage_validator counts it as covered (the writer flagged
    needs_review on its own); we don't double-count failures here.
    """
    report = CoverageReport()
    for topic in topics:
        report.topics_checked += 1
        if not topic.book_examples:
            continue

        narrations = narrations_by_topic.get(topic.topic_id, [])
        covered_refs: set[int] = set()
        for n in narrations:
            if n.example_source == "book" and n.book_example_ref is not None:
                covered_refs.add(n.book_example_ref)
            elif n.example_source == "extended":
                report.extended_beats_emitted += 1

        for ref_idx, be in enumerate(topic.book_examples):
            report.book_examples_total += 1
            if ref_idx in covered_refs:
                report.book_examples_covered += 1
            else:
                gap = CoverageGap(
                    topic_id=topic.topic_id,
                    section_number=topic.section_number,
                    book_example_ref=ref_idx,
                    lesson_focus=be.lesson_focus,
                )
                report.gaps.append(gap)
                logger.warning(
                    "example_coverage.gap "
                    "topic=%s section=%s ref=%d focus=%s",
                    topic.topic_id,
                    topic.section_number,
                    ref_idx,
                    be.lesson_focus,
                )

    return report
