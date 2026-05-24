"""CurriculumAdapter — verifies the duck-typed surface kernel.plan_concept expects."""

from __future__ import annotations

from lecture_pipeline_v2.curriculum.lecture_plan.curriculum_adapter import (
    CurriculumAdapter,
    _LessonPlanShim,
)
from lecture_pipeline_v2.curriculum.lecture_plan.models import ChapterLecturePlan
from lecture_pipeline_v2.curriculum.models import (
    Chapter,
    Diagram,
    DiagramRenderer,
    Topic,
)


def _topic(topic_id: str, name: str, prereqs: list[str] | None = None) -> Topic:
    return Topic(
        topic_id=topic_id,
        chapter_id="ch1",
        section_number="1.1",
        within_chapter_order=1,
        topic_name=name,
        orig_book_content=f"book text for {name}",
        our_understanding=f"understanding of {name}",
        prereq_topic_ids=prereqs or [],
    )


def _chapter() -> Chapter:
    return Chapter(
        chapter_id="ch1",
        chapter_index=1,
        title="Test Chapter",
        summary="s",
        page_start=1,
        page_end=10,
        topic_ids=["t1", "t2", "t3"],
    )


def _lecture_plan() -> ChapterLecturePlan:
    return ChapterLecturePlan(
        chapter_id="ch1",
        chapter_title="Test Chapter",
        chapter_arc="arc",
        opening_hook="hook",
        concept_sequence=["t1", "t2", "t3"],
        length_budget_seconds=600,
        closing_summary="close",
    )


def _diagram(diagram_id: str, description: str) -> Diagram:
    return Diagram(
        diagram_id=diagram_id,
        renderer=DiagramRenderer.SVG,
        render_data={"kind": "stub"},
        description=description,
    )


def test_get_teaching_order_returns_concept_sequence() -> None:
    topics = [_topic("t1", "A"), _topic("t2", "B"), _topic("t3", "C")]
    adapter = CurriculumAdapter(_chapter(), topics, _lecture_plan(), {})

    order = adapter.get_teaching_order()
    uids = [c.uid for c in order]
    assert uids == ["t1", "t2", "t3"]
    # Kernel filters by .level == 0; verify shims set it.
    assert all(c.level == 0 for c in order)


def test_get_prerequisites_returns_known_only() -> None:
    topics = [
        _topic("t1", "A"),
        _topic("t2", "B", prereqs=["t1", "ghost"]),
    ]
    adapter = CurriculumAdapter(_chapter(), topics, _lecture_plan(), {})

    prereqs = adapter.get_prerequisites("t2")
    assert [p.uid for p in prereqs] == ["t1"]


def test_concept_by_uid_returns_shim_with_kernel_surface() -> None:
    topics = [_topic("t1", "Inertia")]
    diagrams = {"t1": [_diagram("d1", "stick figure on a skateboard")]}
    adapter = CurriculumAdapter(_chapter(), topics, _lecture_plan(), diagrams)

    shim = adapter.concept_by_uid("t1")
    assert shim is not None
    # Verify every attribute the kernel reads.
    assert shim.uid == "t1"
    assert shim.topic_name == "Inertia"
    assert shim.level == 0
    assert shim.concept_type == "topic"
    assert shim.difficulty == "medium"
    assert "Inertia" in shim.summary
    assert "Inertia" in shim.source_text
    assert shim.visual_hint == "stick figure on a skateboard"


def test_concept_by_uid_unknown_returns_none() -> None:
    adapter = CurriculumAdapter(_chapter(), [], _lecture_plan(), {})
    assert adapter.concept_by_uid("nope") is None


def test_concepts_list_iterable_for_kernel() -> None:
    topics = [_topic("t1", "A"), _topic("t2", "B")]
    adapter = CurriculumAdapter(_chapter(), topics, _lecture_plan(), {})
    # Kernel iterates over .concepts; verify shape.
    assert len(adapter.concepts) == 2
    assert all(hasattr(c, "level") for c in adapter.concepts)


def test_relationships_empty_iterable() -> None:
    adapter = CurriculumAdapter(_chapter(), [], _lecture_plan(), {})
    # Kernel iterates curriculum.relationships; empty list is fine.
    assert list(adapter.relationships) == []


def test_pre_generated_visuals_keyed_by_uid() -> None:
    topics = [_topic("t1", "A")]
    topics[0].has_diagram_ids = ["d1", "d2"]
    adapter = CurriculumAdapter(_chapter(), topics, _lecture_plan(), {})
    assert "t1" in adapter.pre_generated_visuals
    assert adapter.pre_generated_visuals["t1"]["diagram_ids"] == ["d1", "d2"]


def test_lesson_plan_shim_total_concepts() -> None:
    shim = _LessonPlanShim(total_concepts=7)
    assert shim.total_concepts == 7
