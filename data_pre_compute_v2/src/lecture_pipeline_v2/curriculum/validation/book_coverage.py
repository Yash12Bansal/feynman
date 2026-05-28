"""Hard structural validator for book-example coverage at LessonPlan level.

The Phase-H lesson_pipeline path produces LessonPlan objects (choreography +
crucial_facts + diagrams). The BookExampleWeaver tags every ChoreographyStep
it generates with `is_book_example=True` and `book_example_ref=i`. This
validator checks that every Topic.book_examples[i] has at least one such
step. If not, the chapter ingest is failing the USP.

Unlike `example_coverage.py` (which checks BeatNarrations on the legacy
path), this runs on the lesson_pipeline output BEFORE narration assembly.
That's the right gate to fail the build if coverage is below threshold.

Pure function. No IO.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..lecture_plan.lesson_plan_models import LessonPlan
from ..models import Topic

logger = logging.getLogger(__name__)


@dataclass
class BookCoverageGap:
    topic_id: str
    section_number: str
    book_example_ref: int
    lesson_focus: str


@dataclass
class BookCoverageReport:
    topics_with_examples: int = 0
    total_examples: int = 0
    covered_examples: int = 0
    gaps: list[BookCoverageGap] = field(default_factory=list)

    @property
    def coverage_pct(self) -> float:
        if self.total_examples == 0:
            return 1.0
        return self.covered_examples / self.total_examples

    @property
    def is_passing(self) -> bool:
        """The chapter-level gate. 90% is the floor we agreed on with the
        product owner (2026-05-28); promote toward 100% as the loop tightens.
        """
        return self.coverage_pct >= 0.9

    def summary(self) -> str:
        return (
            f"book-example coverage: "
            f"{self.covered_examples}/{self.total_examples} "
            f"({self.coverage_pct:.0%}); topics_with_examples={self.topics_with_examples}; "
            f"gaps={len(self.gaps)}; "
            f"{'PASS' if self.is_passing else 'FAIL (< 90% floor)'}"
        )


def validate_book_coverage(
    topics: list[Topic],
    lesson_plans_by_topic: dict[str, LessonPlan],
) -> BookCoverageReport:
    """Check every Topic.book_examples[i] has at least one ChoreographyStep
    tagged with is_book_example=True AND book_example_ref==i.

    Topics without book_examples are skipped. Topics without a LessonPlan
    are silently skipped (the lesson_pipeline upstream may have legitimately
    decided to drop them — separate validation concern).
    """
    report = BookCoverageReport()
    for topic in topics:
        if not topic.book_examples:
            continue
        report.topics_with_examples += 1

        plan = lesson_plans_by_topic.get(topic.topic_id)
        if plan is None:
            for ref_idx, be in enumerate(topic.book_examples):
                report.total_examples += 1
                gap = BookCoverageGap(
                    topic_id=topic.topic_id,
                    section_number=topic.section_number,
                    book_example_ref=ref_idx,
                    lesson_focus=be.lesson_focus,
                )
                report.gaps.append(gap)
                logger.warning(
                    "book_coverage.gap_no_plan "
                    "topic=%s section=%s ref=%d focus=%s",
                    topic.topic_id,
                    topic.section_number,
                    ref_idx,
                    be.lesson_focus,
                )
            continue

        covered_refs: set[int] = set()
        for step in plan.choreography:
            if step.is_book_example and step.book_example_ref is not None:
                covered_refs.add(step.book_example_ref)

        for ref_idx, be in enumerate(topic.book_examples):
            report.total_examples += 1
            if ref_idx in covered_refs:
                report.covered_examples += 1
            else:
                gap = BookCoverageGap(
                    topic_id=topic.topic_id,
                    section_number=topic.section_number,
                    book_example_ref=ref_idx,
                    lesson_focus=be.lesson_focus,
                )
                report.gaps.append(gap)
                logger.warning(
                    "book_coverage.gap "
                    "topic=%s section=%s ref=%d focus=%s",
                    topic.topic_id,
                    topic.section_number,
                    ref_idx,
                    be.lesson_focus,
                )

    return report
