"""Bridge v2's Chapter+Topic[] data model to the duck-typed surface that
feynman_teaching_kernel.plan_concept expects.

The kernel's `curriculum` parameter is typed `Any` but reads these attributes
(per planner.py inspection):
  - get_teaching_order() -> Iterable[Concept], each with `.level`, `.topic_name`,
    `.uid`, `.concept_type`, `.difficulty`, `.summary`, `.source_text`,
    `.visual_hint`
  - get_prerequisites(uid) -> Iterable[Concept], each with `.topic_name`
  - concept_by_uid(uid) -> Concept | None
  - .concepts: Iterable[Concept] (used to filter detail nodes — kernel filters
    by `c.level == 1`)
  - .relationships: Iterable[Edge], each with `.from_uid`, `.to_uid`, `.rel_type`
  - .pre_generated_visuals: dict[uid, Any]

The kernel also reads `plan.total_concepts` (we expose `_LessonPlanShim`
separately because v2's ChapterLecturePlan is not the kernel's "plan").
"""

from __future__ import annotations

from typing import Any

from lecture_pipeline_v2.curriculum.lecture_plan.models import ChapterLecturePlan
from lecture_pipeline_v2.curriculum.models import Diagram, Topic


class _ConceptShim:
    """v2 Topic projected onto the kernel's `Concept` duck-typed surface.

    `level` is always 0 because v2 topics map to top-level concepts (the
    kernel uses `level == 1` for sub-topic detail nodes — we have none).
    """

    def __init__(self, topic: Topic, diagrams: list[Diagram]) -> None:
        self.uid: str = topic.topic_id
        self.topic_name: str = topic.topic_name
        self.level: int = 0
        # v2 doesn't track concept_type / difficulty; defaults keep the
        # kernel prompt sensible without affecting LLM output quality.
        self.concept_type: str = "topic"
        self.difficulty: str = "medium"
        self.summary: str = topic.our_understanding or ""
        self.source_text: str = topic.orig_book_content or ""
        self.visual_hint: str = diagrams[0].description if diagrams else ""
        # Escape hatch — keep the raw topic accessible if a downstream
        # adapter wants to peek at examples / question ids / etc.
        self.topic: Topic = topic


class _LessonPlanShim:
    """v2 equivalent of the kernel's `plan` arg — exposes `.total_concepts`."""

    def __init__(self, total_concepts: int) -> None:
        self.total_concepts: int = total_concepts


class CurriculumAdapter:
    """Wraps a v2 Chapter + Topic[] + ChapterLecturePlan for the kernel.

    Construction:
        adapter = CurriculumAdapter(chapter, topics, lecture_plan, diagrams_by_topic)
        plan = await plan_concept(idx, curriculum=adapter, plan=_LessonPlanShim(N), ...)

    The kernel iterates `curriculum.get_teaching_order()` (filtered to
    `level == 0`) to find concepts to plan; uses `concept_index` to index
    into that filtered list.
    """

    def __init__(
        self,
        chapter: Any,
        topics: list[Topic],
        lecture_plan: ChapterLecturePlan,
        diagrams_by_topic: dict[str, list[Diagram]],
    ) -> None:
        self._chapter = chapter
        self._lecture_plan = lecture_plan
        self._topics_by_id: dict[str, Topic] = {t.topic_id: t for t in topics}
        self._concepts_by_uid: dict[str, _ConceptShim] = {
            t.topic_id: _ConceptShim(t, diagrams_by_topic.get(t.topic_id, []))
            for t in topics
        }
        # Public surface the kernel reads
        self.concepts: list[_ConceptShim] = list(self._concepts_by_uid.values())
        self.relationships: list[Any] = []  # kernel only iterates; empty is fine
        self.pre_generated_visuals: dict[str, dict[str, Any]] = {
            t.topic_id: {"diagram_ids": list(t.has_diagram_ids)}
            for t in topics
            if t.has_diagram_ids
        }

    def get_teaching_order(self) -> list[_ConceptShim]:
        """Return concepts in the order ChapterLecturePlanner decided.

        Kernel filters this list by `level == 0` (every concept here is 0).
        """
        ordered: list[_ConceptShim] = []
        for uid in self._lecture_plan.concept_sequence:
            shim = self._concepts_by_uid.get(uid)
            if shim is not None:
                ordered.append(shim)
        return ordered

    def get_prerequisites(self, uid: str) -> list[_ConceptShim]:
        topic = self._topics_by_id.get(uid)
        if topic is None:
            return []
        return [
            self._concepts_by_uid[prereq_uid]
            for prereq_uid in topic.prereq_topic_ids
            if prereq_uid in self._concepts_by_uid
        ]

    def concept_by_uid(self, uid: str) -> _ConceptShim | None:
        return self._concepts_by_uid.get(uid)
