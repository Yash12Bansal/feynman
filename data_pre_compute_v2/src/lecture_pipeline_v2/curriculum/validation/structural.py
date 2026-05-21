"""Structural validation — deterministic checks, no LLM calls.

Checks: duplicate IDs, dangling references, required fields, hierarchy
consistency, prereq cycles, anchored-section coverage.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from ..anchors.models import ExtractionAnchors
from ..models import CurriculumExtractionResult
from .models import ValidationReport

logger = logging.getLogger(__name__)


class StructuralValidator:
    def validate(
        self,
        extraction: CurriculumExtractionResult,
        anchors_by_chapter: dict[str, ExtractionAnchors] | None = None,
    ) -> ValidationReport:
        report = ValidationReport(
            topics_checked=len(extraction.topics),
            diagrams_checked=len(extraction.diagrams),
            questions_checked=len(extraction.questions),
        )

        self._check_duplicate_ids(extraction, report)
        self._check_required_fields(extraction, report)
        self._check_referential_integrity(extraction, report)
        self._check_next_chain(extraction, report)
        self._check_prereq_cycles(extraction, report)

        if anchors_by_chapter:
            self._check_section_coverage(extraction, anchors_by_chapter, report)

        logger.info(report.summary())
        return report

    def _check_duplicate_ids(self, extraction, report: ValidationReport) -> None:
        for collection, attr in [
            (extraction.chapters, "chapter_id"),
            (extraction.topics, "topic_id"),
            (extraction.diagrams, "diagram_id"),
            (extraction.questions, "question_id"),
        ]:
            seen: set[str] = set()
            for item in collection:
                uid = getattr(item, attr)
                if uid in seen:
                    report.add_error(
                        "DUPLICATE_ID",
                        f"Duplicate {attr}: {uid}",
                        entity_id=uid,
                    )
                seen.add(uid)

    def _check_required_fields(self, extraction, report: ValidationReport) -> None:
        for topic in extraction.topics:
            if not topic.topic_name.strip():
                report.add_error("EMPTY_TOPIC_NAME", f"{topic.topic_id} has empty name",
                                 entity_id=topic.topic_id)
            if not topic.our_understanding.strip():
                report.add_warning("EMPTY_UNDERSTANDING",
                                   f"{topic.topic_id} has empty our_understanding",
                                   entity_id=topic.topic_id)
            if not topic.orig_book_content.strip():
                report.add_warning("EMPTY_SOURCE",
                                   f"{topic.topic_id} has empty orig_book_content",
                                   entity_id=topic.topic_id)

        for q in extraction.questions:
            if not q.q_text.strip() or not q.answer.strip():
                report.add_error("INCOMPLETE_QUESTION",
                                 f"{q.question_id} missing q_text or answer",
                                 entity_id=q.question_id)
            if q.type.value == "mcq" and len(q.options) < 2:
                report.add_error("MCQ_FEW_OPTIONS",
                                 f"{q.question_id} MCQ has <2 options",
                                 entity_id=q.question_id)

    def _check_referential_integrity(self, extraction, report: ValidationReport) -> None:
        chapter_ids = {c.chapter_id for c in extraction.chapters}
        topic_ids = {t.topic_id for t in extraction.topics}
        diagram_ids = {d.diagram_id for d in extraction.diagrams}
        question_ids = {q.question_id for q in extraction.questions}

        for topic in extraction.topics:
            if topic.chapter_id not in chapter_ids:
                report.add_error("DANGLING_CHAPTER_REF",
                                 f"{topic.topic_id} points to missing chapter {topic.chapter_id}",
                                 entity_id=topic.topic_id)
            if topic.next_topic_id and topic.next_topic_id not in topic_ids:
                report.add_error("DANGLING_NEXT",
                                 f"{topic.topic_id} next_topic_id missing: {topic.next_topic_id}",
                                 entity_id=topic.topic_id)
            for pid in topic.prereq_topic_ids:
                if pid not in topic_ids:
                    report.add_error("DANGLING_PREREQ",
                                     f"{topic.topic_id} prereq missing: {pid}",
                                     entity_id=topic.topic_id)
            for did in topic.has_diagram_ids:
                if did not in diagram_ids:
                    report.add_error("DANGLING_DIAGRAM",
                                     f"{topic.topic_id} diagram missing: {did}",
                                     entity_id=topic.topic_id)
            for qid in topic.has_question_ids:
                if qid not in question_ids:
                    report.add_error("DANGLING_QUESTION",
                                     f"{topic.topic_id} question missing: {qid}",
                                     entity_id=topic.topic_id)

        for chapter in extraction.chapters:
            for tid in chapter.topic_ids:
                if tid not in topic_ids:
                    report.add_error("DANGLING_CHAPTER_TOPIC",
                                     f"{chapter.chapter_id} topic missing: {tid}",
                                     entity_id=chapter.chapter_id)

    def _check_next_chain(self, extraction, report: ValidationReport) -> None:
        by_chapter: dict[str, list] = defaultdict(list)
        for topic in extraction.topics:
            by_chapter[topic.chapter_id].append(topic)
        for chapter_id, topics in by_chapter.items():
            topics.sort(key=lambda t: t.within_chapter_order)
            for i, t in enumerate(topics):
                expected_next = topics[i + 1].topic_id if i + 1 < len(topics) else None
                if t.next_topic_id != expected_next:
                    report.add_warning(
                        "NEXT_CHAIN_GAP",
                        f"{t.topic_id} next_topic_id={t.next_topic_id} "
                        f"but expected {expected_next}",
                        entity_id=t.topic_id,
                    )

    def _check_prereq_cycles(self, extraction, report: ValidationReport) -> None:
        graph: dict[str, list[str]] = defaultdict(list)
        for topic in extraction.topics:
            for pid in topic.prereq_topic_ids:
                graph[topic.topic_id].append(pid)
        if not graph:
            return

        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {t.topic_id: WHITE for t in extraction.topics}

        def dfs(u: str, path: list[str]) -> list[str] | None:
            color[u] = GRAY
            path.append(u)
            for v in graph.get(u, []):
                if color.get(v) == GRAY:
                    return path + [v]
                if color.get(v) == WHITE:
                    cycle = dfs(v, path)
                    if cycle:
                        return cycle
            path.pop()
            color[u] = BLACK
            return None

        for topic_id in list(color.keys()):
            if color[topic_id] == WHITE and topic_id in graph:
                cycle = dfs(topic_id, [])
                if cycle:
                    report.add_error(
                        "CIRCULAR_PREREQ",
                        f"Circular prereq chain: {' → '.join(cycle)}",
                    )
                    return

    def _check_section_coverage(
        self,
        extraction,
        anchors_by_chapter: dict[str, ExtractionAnchors],
        report: ValidationReport,
    ) -> None:
        topics_by_chapter: dict[str, set[str]] = defaultdict(set)
        for topic in extraction.topics:
            topics_by_chapter[topic.chapter_id].add(topic.section_number)

        for chapter_id, anchors in anchors_by_chapter.items():
            extracted_sections = topics_by_chapter.get(chapter_id, set())
            missing = []
            for s in anchors.section_numbers:
                if s.section_number not in extracted_sections:
                    missing.append(f"{s.section_number} {s.title}")
            if missing:
                report.add_warning(
                    "MISSING_SECTIONS",
                    f"{chapter_id}: {len(missing)}/{len(anchors.section_numbers)} sections "
                    f"have no Topic node. First few: {missing[:3]}",
                    entity_id=chapter_id,
                    details={"missing_sections": missing},
                )
