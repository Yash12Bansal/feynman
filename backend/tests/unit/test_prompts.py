"""Tests for dynamic prompt building."""

from uuid import uuid4

from feynman.agent.lesson_plan import ConceptNode, LessonPlan
from feynman.agent.prompts import (
    STATE_TOOL_INSTRUCTIONS,
    TEACHING_SYSTEM_PROMPT,
    ZONE_PLACEMENT_INSTRUCTIONS,
    build_teaching_prompt,
)
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


class TestBuildTeachingPromptNoPlan:
    def test_includes_base_prompt(self):
        ctx = _make_ctx(plan=None)
        prompt = build_teaching_prompt(None, ctx)
        assert TEACHING_SYSTEM_PROMPT in prompt

    def test_free_form_mode(self):
        ctx = _make_ctx(plan=None)
        prompt = build_teaching_prompt(None, ctx)
        assert "free-form teaching mode" in prompt

    def test_no_state_tools(self):
        ctx = _make_ctx(plan=None)
        prompt = build_teaching_prompt(None, ctx)
        assert "advance_concept" not in prompt


class TestBuildTeachingPromptWithPlan:
    def test_includes_base_prompt(self):
        plan = _make_plan()
        ctx = _make_ctx(plan=plan)
        prompt = build_teaching_prompt(plan, ctx)
        assert TEACHING_SYSTEM_PROMPT in prompt

    def test_includes_state_tools(self):
        plan = _make_plan()
        ctx = _make_ctx(plan=plan)
        prompt = build_teaching_prompt(plan, ctx)
        assert STATE_TOOL_INSTRUCTIONS in prompt

    def test_includes_topic(self):
        plan = _make_plan()
        ctx = _make_ctx(plan=plan)
        prompt = build_teaching_prompt(plan, ctx)
        assert "Quadratic Equations" in prompt

    def test_includes_grade_level(self):
        plan = _make_plan()
        ctx = _make_ctx(plan=plan)
        prompt = build_teaching_prompt(plan, ctx)
        assert "Grade 10" in prompt

    def test_includes_objective(self):
        plan = _make_plan()
        ctx = _make_ctx(plan=plan)
        prompt = build_teaching_prompt(plan, ctx)
        assert "Solve quadratics" in prompt

    def test_shows_concept_list(self):
        plan = _make_plan(3)
        ctx = _make_ctx(plan=plan)
        prompt = build_teaching_prompt(plan, ctx)
        assert "Concept 1" in prompt
        assert "Concept 2" in prompt
        assert "Concept 3" in prompt

    def test_current_marker(self):
        plan = _make_plan(3)
        ctx = _make_ctx(plan=plan)
        prompt = build_teaching_prompt(plan, ctx)
        assert "[>> CURRENT]" in prompt
        assert "Now Teaching: Concept 1" in prompt

    def test_shows_key_points(self):
        plan = _make_plan()
        ctx = _make_ctx(plan=plan)
        prompt = build_teaching_prompt(plan, ctx)
        assert "point 1" in prompt
        assert "point 2" in prompt

    def test_shows_visual_suggestions(self):
        plan = _make_plan()
        ctx = _make_ctx(plan=plan)
        prompt = build_teaching_prompt(plan, ctx)
        assert "diagram" in prompt


class TestBuildTeachingPromptAfterAdvance:
    def test_done_markers(self):
        plan = _make_plan(3)
        ctx = _make_ctx(plan=plan)
        ctx.advance()  # Concept 1 done, now on Concept 2
        prompt = build_teaching_prompt(plan, ctx)
        assert "[DONE]" in prompt
        assert "Now Teaching: Concept 2" in prompt


class TestBuildTeachingPromptDoubtBranch:
    async def test_branch_context(self):
        plan = _make_plan(3)
        ctx = _make_ctx(plan=plan)
        await ctx.state_machine.push_branch(concept="why x squared?")
        prompt = build_teaching_prompt(plan, ctx)
        assert "DOUBT BRANCH" in prompt
        assert "why x squared?" in prompt
        assert "resolve_doubt()" in prompt

    async def test_nested_branches(self):
        plan = _make_plan(3)
        ctx = _make_ctx(plan=plan)
        await ctx.state_machine.push_branch(concept="doubt 1")
        await ctx.state_machine.push_branch(concept="doubt 2")
        prompt = build_teaching_prompt(plan, ctx)
        assert "depth 3" in prompt
        assert "doubt 2" in prompt


class TestBuildTeachingPromptLessonComplete:
    def test_complete(self):
        plan = _make_plan(2)
        ctx = _make_ctx(plan=plan)
        ctx.advance()
        ctx.advance()
        prompt = build_teaching_prompt(plan, ctx)
        assert "LESSON COMPLETE" in prompt
        assert "Summarize" in prompt


class TestZonePlacementInstructions:
    def test_included_with_plan(self):
        plan = _make_plan()
        ctx = _make_ctx(plan=plan)
        prompt = build_teaching_prompt(plan, ctx)
        assert ZONE_PLACEMENT_INSTRUCTIONS in prompt

    def test_included_without_plan(self):
        ctx = _make_ctx(plan=None)
        prompt = build_teaching_prompt(None, ctx)
        assert ZONE_PLACEMENT_INSTRUCTIONS in prompt

    def test_zone_names_listed(self):
        ctx = _make_ctx(plan=None)
        prompt = build_teaching_prompt(None, ctx)
        assert "top-left" in prompt
        assert "center-center" in prompt
        assert "bottom-right" in prompt


class TestBoardStateInPrompt:
    def test_empty_board_state(self):
        ctx = _make_ctx(plan=None)
        prompt = build_teaching_prompt(None, ctx)
        assert "Board State" in prompt
        assert "Board is empty." in prompt

    def test_board_state_with_elements(self):
        from feynman.visuals.schemas import BoardZone, ShowTextInstruction

        ctx = _make_ctx(plan=None)
        ctx.board_manager.record(
            ShowTextInstruction(
                text="Key formula",
                element_id="text-1",
                zone=BoardZone.TOP_CENTER,
            )
        )
        prompt = build_teaching_prompt(None, ctx)
        assert "Board State" in prompt
        assert "text-1" in prompt
        assert "Key formula" in prompt
        assert "top-center" in prompt

    def test_board_state_section_in_plan_mode(self):
        from feynman.visuals.schemas import ShowEquationInstruction

        plan = _make_plan()
        ctx = _make_ctx(plan=plan)
        ctx.board_manager.record(
            ShowEquationInstruction(
                latex="E = mc^2",
                label="Einstein",
                element_id="eq-1",
            )
        )
        prompt = build_teaching_prompt(plan, ctx)
        assert "Board State" in prompt
        assert "eq-1" in prompt
        assert "Einstein" in prompt
