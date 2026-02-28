"""Tests for TeachingContext — progression, completion, and summary."""

from uuid import uuid4

from feynman.agent.lesson_plan import ConceptNode, LessonPlan
from feynman.agent.state_machine import TeachingStateMachine
from feynman.agent.teaching_context import TeachingContext
from feynman.common.types import Subject


def _make_concept(title: str) -> ConceptNode:
    return ConceptNode(
        title=title,
        description=f"Teach {title}",
        key_points=["point 1", "point 2"],
        visual_suggestions=["diagram"],
    )


def _make_plan(num_concepts: int = 3) -> LessonPlan:
    return LessonPlan(
        topic="Quadratic Equations",
        subject=Subject.MATH,
        grade_level="Grade 10",
        objective="Solve quadratics",
        concepts=[_make_concept(f"Concept {i + 1}") for i in range(num_concepts)],
    )


def _make_ctx(plan: LessonPlan | None = None) -> TeachingContext:
    session_id = uuid4()
    sm = TeachingStateMachine(session_id=session_id)
    return TeachingContext(
        session_id=session_id,
        state_machine=sm,
        lesson_plan=plan,
    )


class TestCurrentConcept:
    def test_no_plan(self):
        ctx = _make_ctx(plan=None)
        assert ctx.current_concept is None

    def test_with_plan(self):
        ctx = _make_ctx(plan=_make_plan(3))
        assert ctx.current_concept is not None
        assert ctx.current_concept.title == "Concept 1"

    def test_after_advance(self):
        ctx = _make_ctx(plan=_make_plan(3))
        ctx.advance()
        assert ctx.current_concept.title == "Concept 2"


class TestAdvance:
    def test_basic_progression(self):
        ctx = _make_ctx(plan=_make_plan(3))
        assert ctx.current_concept_index == 0

        next_concept = ctx.advance()
        assert next_concept is not None
        assert next_concept.title == "Concept 2"
        assert ctx.current_concept_index == 1
        assert 0 in ctx.completed_indices

    def test_advance_to_end(self):
        ctx = _make_ctx(plan=_make_plan(2))
        ctx.advance()  # 0 -> 1
        result = ctx.advance()  # 1 -> done
        assert result is None
        assert ctx.completed_indices == [0, 1]

    def test_advance_no_plan(self):
        ctx = _make_ctx(plan=None)
        assert ctx.advance() is None

    def test_no_duplicate_completed(self):
        ctx = _make_ctx(plan=_make_plan(3))
        ctx.advance()
        # Manually try to advance again from same index (shouldn't happen
        # but let's verify no duplicate entries)
        ctx.current_concept_index = 1
        ctx.advance()
        assert ctx.completed_indices.count(1) == 1


class TestIsLessonComplete:
    def test_no_plan(self):
        ctx = _make_ctx(plan=None)
        assert ctx.is_lesson_complete is False

    def test_not_complete(self):
        ctx = _make_ctx(plan=_make_plan(3))
        assert ctx.is_lesson_complete is False

    def test_complete_after_all_concepts(self):
        ctx = _make_ctx(plan=_make_plan(2))
        ctx.advance()  # 0 -> 1
        ctx.advance()  # 1 -> done
        assert ctx.is_lesson_complete is True

    def test_partially_complete(self):
        ctx = _make_ctx(plan=_make_plan(3))
        ctx.advance()  # 0 -> 1
        assert ctx.is_lesson_complete is False


class TestProgressSummary:
    def test_no_plan(self):
        ctx = _make_ctx(plan=None)
        assert "Free-form" in ctx.progress_summary

    def test_initial(self):
        ctx = _make_ctx(plan=_make_plan(3))
        summary = ctx.progress_summary
        assert "0/3" in summary
        assert "Concept 1" in summary

    def test_after_advance(self):
        ctx = _make_ctx(plan=_make_plan(3))
        ctx.advance()
        summary = ctx.progress_summary
        assert "1/3" in summary
        assert "Concept 2" in summary

    async def test_with_branch(self):
        ctx = _make_ctx(plan=_make_plan(3))
        await ctx.state_machine.push_branch(concept="doubt")
        summary = ctx.progress_summary
        assert "Branch depth: 2" in summary
