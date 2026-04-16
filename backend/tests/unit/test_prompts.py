"""Tests for dynamic prompt building."""

from uuid import uuid4

from feynman.agent.lesson_plan import ConceptNode, LessonPlan
from feynman.agent.prompts import (
    BOARD_RELATIONSHIPS_INSTRUCTIONS,
    PLACEMENT_INSTRUCTIONS,
    SCENE_INSTRUCTIONS,
    STATE_TOOL_INSTRUCTIONS,
    TEACHING_SYSTEM_PROMPT,
    TOOL_ROUTING_INSTRUCTIONS,
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
        assert "Now Teaching [1 of 3]: Concept 1" in prompt

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
        assert "Now Teaching [2 of 3]: Concept 2" in prompt


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


class TestPlacementInstructions:
    def test_included_with_plan(self):
        plan = _make_plan()
        ctx = _make_ctx(plan=plan)
        prompt = build_teaching_prompt(plan, ctx)
        assert PLACEMENT_INSTRUCTIONS in prompt

    def test_included_without_plan(self):
        ctx = _make_ctx(plan=None)
        prompt = build_teaching_prompt(None, ctx)
        assert PLACEMENT_INSTRUCTIONS in prompt

    def test_near_and_near_side_documented(self):
        assert "near=" in PLACEMENT_INSTRUCTIONS
        assert "near_side=" in PLACEMENT_INSTRUCTIONS

    def test_three_placement_options(self):
        assert "Option 1: Near an existing element" in PLACEMENT_INSTRUCTIONS
        assert "Option 2: Zone placement" in PLACEMENT_INSTRUCTIONS
        assert "Option 3: Auto-placement" in PLACEMENT_INSTRUCTIONS

    def test_pattern_concept_introduction(self):
        assert "Concept Introduction" in PLACEMENT_INSTRUCTIONS

    def test_pattern_step_by_step_derivation(self):
        assert "Step-by-step Derivation" in PLACEMENT_INSTRUCTIONS

    def test_pattern_problem_solving(self):
        assert "Problem Solving" in PLACEMENT_INSTRUCTIONS

    def test_pattern_comparison(self):
        assert "Comparison" in PLACEMENT_INSTRUCTIONS
        assert "Case A" in PLACEMENT_INSTRUCTIONS
        assert "Case B" in PLACEMENT_INSTRUCTIONS

    def test_spatial_rules_present(self):
        rules = PLACEMENT_INSTRUCTIONS
        assert "Related" in rules
        assert "Reading flow" in rules
        assert "anchor" in rules
        assert "snapshot" in rules
        assert "Size matters" in rules

    def test_size_hint_documented(self):
        assert 'size_hint="large"' in PLACEMENT_INSTRUCTIONS
        assert '"small"' in PLACEMENT_INSTRUCTIONS


class TestToolRoutingInstructions:
    def test_included_with_plan(self):
        plan = _make_plan()
        ctx = _make_ctx(plan=plan)
        prompt = build_teaching_prompt(plan, ctx)
        assert TOOL_ROUTING_INSTRUCTIONS in prompt

    def test_included_without_plan(self):
        ctx = _make_ctx(plan=None)
        prompt = build_teaching_prompt(None, ctx)
        assert TOOL_ROUTING_INSTRUCTIONS in prompt

    def test_all_tools_routed(self):
        """Every visual tool must appear in the routing table."""
        for tool in (
            "show_text",
            "show_equation",
            "step_equation",
            "draw_design_diagram",
            "modify_design_diagram",
            "draw_scene",
            "draw_diagram",
            "show_graph",
        ):
            assert tool in TOOL_ROUTING_INSTRUCTIONS, f"{tool} missing from routing"

    def test_decision_rules_present(self):
        assert "Decision rules" in TOOL_ROUTING_INSTRUCTIONS
        assert "NEVER put plain text" in TOOL_ROUTING_INSTRUCTIONS
        assert "NEVER draw a diagram just" in TOOL_ROUTING_INSTRUCTIONS

    def test_appears_before_individual_tool_sections(self):
        """Routing section should appear before detailed tool instructions."""
        ctx = _make_ctx(plan=None)
        prompt = build_teaching_prompt(None, ctx)
        routing_pos = prompt.index("Tool Routing")
        design_pos = prompt.index("Detailed Diagrams")
        scene_pos = prompt.index("Scientific Diagrams")
        assert routing_pos < design_pos
        assert routing_pos < scene_pos

    def test_no_contradictory_prefer_guidance(self):
        """Old 'Prefer this over draw_scene' should be gone from design instructions."""
        ctx = _make_ctx(plan=None)
        prompt = build_teaching_prompt(None, ctx)
        assert "Prefer this over" not in prompt


class TestSceneInstructions:
    def test_included_with_plan(self):
        plan = _make_plan()
        ctx = _make_ctx(plan=plan)
        prompt = build_teaching_prompt(plan, ctx)
        assert SCENE_INSTRUCTIONS in prompt

    def test_included_without_plan(self):
        ctx = _make_ctx(plan=None)
        prompt = build_teaching_prompt(None, ctx)
        assert SCENE_INSTRUCTIONS in prompt

    def test_all_scene_types_documented(self):
        for scene_type in ("free_body", "optics", "circuit", "geometry", "chemistry"):
            assert scene_type in SCENE_INSTRUCTIONS, f"{scene_type} not documented"

    def test_few_shot_examples_present(self):
        for kind in ("box", "convex_lens", "battery", "triangle", "molecule", "beaker"):
            assert kind in SCENE_INSTRUCTIONS, f"few-shot example missing {kind}"

    def test_auto_generation_documented(self):
        assert "auto-generate" in SCENE_INSTRUCTIONS.lower()

    def test_incremental_build_documented(self):
        assert "incremental" in SCENE_INSTRUCTIONS.lower()
        assert "clear_board" in SCENE_INSTRUCTIONS

    def test_legacy_templates_mentioned(self):
        assert "template_id" in SCENE_INSTRUCTIONS
        assert "free_body" in SCENE_INSTRUCTIONS
        assert "double_slit" in SCENE_INSTRUCTIONS


class TestBoardStateInPrompt:
    def test_empty_board_state(self):
        ctx = _make_ctx(plan=None)
        prompt = build_teaching_prompt(None, ctx)
        assert "Board State" in prompt
        assert "Board is empty." in prompt


class TestAdvanceConceptInstructions:
    """Phase 1: advance_concept must be clearly prompted."""

    def test_one_concept_at_a_time_in_state_tools(self):
        assert "One concept at a time" in STATE_TOOL_INSTRUCTIONS

    def test_explicit_advance_call_instruction(self):
        assert "call advance_concept()" in STATE_TOOL_INSTRUCTIONS

    def test_do_not_teach_next(self):
        assert "Do NOT teach the next concept" in STATE_TOOL_INSTRUCTIONS

    def test_progress_indicator_format(self):
        plan = _make_plan(5)
        ctx = _make_ctx(plan=plan)
        prompt = build_teaching_prompt(plan, ctx)
        assert "[1 of 5]" in prompt

    def test_completion_checklist_present(self):
        plan = _make_plan()
        ctx = _make_ctx(plan=plan)
        prompt = build_teaching_prompt(plan, ctx)
        assert "Completion checklist" in prompt
        assert "Covered each key point" in prompt
        assert "Showed at least one visual" in prompt
        assert "Paused for student questions" in prompt

    def test_checklist_absent_when_lesson_complete(self):
        plan = _make_plan(1)
        ctx = _make_ctx(plan=plan)
        ctx.advance()  # marks concept 0 done, no next concept
        prompt = build_teaching_prompt(plan, ctx)
        assert "Completion checklist" not in prompt


class TestTeachingReference:
    """Phase 2: ConceptGraph content reaches the agent."""

    def test_teaching_reference_with_graph_node(self):
        plan = _make_plan()
        ctx = _make_ctx(plan=plan)
        # Mock a graph node with a rich summary
        _mock = type("N", (), {
            "summary": "A detailed explanation of quadratic equations including "
                       "the discriminant b²-4ac, vertex form, and factoring.",
            "node_id": "n1",
            "topic_name": "Concept 1",
        })()
        ctx._graph_node_map = {0: "n1"}
        ctx.concept_graph = type("G", (), {
            "nodes": {"n1": _mock},
            "get_related_edges": lambda self, nid: [],
        })()
        prompt = build_teaching_prompt(plan, ctx)
        assert "Teaching reference" in prompt
        assert "discriminant" in prompt

    def test_no_teaching_reference_without_graph(self):
        plan = _make_plan()
        ctx = _make_ctx(plan=plan)
        prompt = build_teaching_prompt(plan, ctx)
        assert "Teaching reference" not in prompt

    def test_summary_truncated_at_800(self):
        plan = _make_plan()
        ctx = _make_ctx(plan=plan)
        _mock = type("N", (), {
            "summary": "x" * 1000,
            "node_id": "n1",
            "topic_name": "Concept 1",
        })()
        ctx._graph_node_map = {0: "n1"}
        ctx.concept_graph = type("G", (), {
            "nodes": {"n1": _mock},
            "get_related_edges": lambda self, nid: [],
        })()
        prompt = build_teaching_prompt(plan, ctx)
        assert "Teaching reference" in prompt
        # Summary should be truncated — not all 1000 x's.
        # Allow a few extra from surrounding prompt text that contains 'x'.
        ref_start = prompt.index("Teaching reference")
        ref_section = prompt[ref_start:ref_start + 1200]
        assert ref_section.count("x") <= 810


class TestPreRenderedVisuals:
    """Phase 3: Pre-generated prompts shown to agent."""

    def test_pre_rendered_when_anticipation_has_prompts(self):
        plan = _make_plan()
        ctx = _make_ctx(plan=plan)
        # Seed the anticipation cache directly
        ctx.anticipation._prompts[(0, 0)] = "Draw a force diagram"
        prompt = build_teaching_prompt(plan, ctx)
        assert "Pre-rendered visuals" in prompt
        assert "Draw a force diagram" in prompt
        assert "instant rendering" in prompt

    def test_visual_suggestions_fallback_when_no_anticipation(self):
        plan = _make_plan()
        ctx = _make_ctx(plan=plan)
        prompt = build_teaching_prompt(plan, ctx)
        assert "Pre-rendered visuals" not in prompt
        assert "Visual suggestions:" in prompt
        assert "diagram" in prompt

    def test_visual_suggestions_relabeled_when_anticipation_present(self):
        plan = _make_plan()
        ctx = _make_ctx(plan=plan)
        ctx.anticipation._prompts[(0, 0)] = "Draw a lens diagram"
        prompt = build_teaching_prompt(plan, ctx)
        assert "Additional visual ideas:" in prompt
        assert "Visual suggestions:" not in prompt

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


class TestScrollInstructions:
    """Phase 4A: Scroll instructions and viewport-aware board state."""

    def test_scroll_instructions_in_prompt(self):
        from feynman.agent.prompts import SCROLL_INSTRUCTIONS

        ctx = _make_ctx(plan=None)
        prompt = build_teaching_prompt(None, ctx)
        assert SCROLL_INSTRUCTIONS in prompt

    def test_scroll_instructions_content(self):
        from feynman.agent.prompts import SCROLL_INSTRUCTIONS

        assert "infinite canvas" in SCROLL_INSTRUCTIONS
        assert "scroll_board()" in SCROLL_INSTRUCTIONS
        assert "scroll right" in SCROLL_INSTRUCTIONS.lower()

    def test_fullness_hint_when_crowded(self):
        from feynman.visuals.schemas import BoardZone, ShowTextInstruction

        ctx = _make_ctx(plan=None)
        # Fill 6 zones to trigger fullness hint
        zones = list(BoardZone)[:6]
        for i, zone in enumerate(zones):
            ctx.board_manager.record(
                ShowTextInstruction(
                    text=f"content {i}",
                    element_id=f"text-{i + 1}",
                    zone=zone,
                )
            )
        prompt = build_teaching_prompt(None, ctx)
        assert "**Board is filling up**" in prompt

    def test_no_fullness_hint_when_sparse(self):
        from feynman.visuals.schemas import BoardZone, ShowTextInstruction

        ctx = _make_ctx(plan=None)
        ctx.board_manager.record(
            ShowTextInstruction(
                text="solo",
                element_id="text-1",
                zone=BoardZone.CENTER_CENTER,
            )
        )
        prompt = build_teaching_prompt(None, ctx)
        assert "**Board is filling up**" not in prompt

    def test_viewport_position_shown_when_scrolled(self):

        ctx = _make_ctx(plan=None)
        # Scroll to tile (1, 0)
        ctx.board_manager.active_board.state.scroll_to_tile(1, 0)
        prompt = build_teaching_prompt(None, ctx)
        assert "Tile (1, 0)" in prompt

    def test_offscreen_summary_shown(self):
        from feynman.visuals.schemas import BoardZone, ShowTextInstruction

        ctx = _make_ctx(plan=None)
        # Place element at tile (0, 0)
        ctx.board_manager.record(
            ShowTextInstruction(
                text="earlier content",
                element_id="text-1",
                zone=BoardZone.CENTER_CENTER,
            )
        )
        # Scroll away to tile (1, 0)
        ctx.board_manager.active_board.state.scroll_to_tile(1, 0)
        prompt = build_teaching_prompt(None, ctx)
        assert "Off-screen" in prompt
        assert "left" in prompt


class TestBoardStateCameraAndTiles:
    """Phase 4A: BoardState camera state and tile tracking."""

    def test_initial_camera_at_origin(self):
        from feynman.agent.board_state import BoardState

        bs = BoardState()
        assert bs.camera_tile_x == 0
        assert bs.camera_tile_y == 0

    def test_scroll_to_tile(self):
        from feynman.agent.board_state import BoardState

        bs = BoardState()
        bs.scroll_to_tile(2, 1)
        assert bs.camera_tile_x == 2
        assert bs.camera_tile_y == 1

    def test_element_stamped_with_tile(self):
        from feynman.visuals.schemas import ShowTextInstruction

        ctx = _make_ctx(plan=None)
        state = ctx.board_manager.active_board.state
        state.scroll_to_tile(1, 0)
        ctx.board_manager.record(
            ShowTextInstruction(
                text="test",
                element_id="text-1",
            )
        )
        el = state._elements["text-1"]
        assert el.tile_x == 1
        assert el.tile_y == 0

    def test_visible_elements_filters_by_tile(self):
        from feynman.visuals.schemas import BoardZone, ShowTextInstruction

        ctx = _make_ctx(plan=None)
        state = ctx.board_manager.active_board.state

        # Element at tile (0, 0)
        ctx.board_manager.record(
            ShowTextInstruction(text="a", element_id="text-1", zone=BoardZone.TOP_LEFT)
        )
        # Scroll and add element at tile (1, 0)
        state.scroll_to_tile(1, 0)
        ctx.board_manager.record(
            ShowTextInstruction(text="b", element_id="text-2", zone=BoardZone.TOP_LEFT)
        )

        visible = state.visible_elements()
        assert "text-2" in visible
        assert "text-1" not in visible

    def test_visible_free_zones(self):
        from feynman.visuals.schemas import BoardZone, ShowTextInstruction

        ctx = _make_ctx(plan=None)
        state = ctx.board_manager.active_board.state

        ctx.board_manager.record(
            ShowTextInstruction(text="a", element_id="text-1", zone=BoardZone.TOP_LEFT)
        )
        # Scroll to fresh tile — all zones should be free
        state.scroll_to_tile(1, 0)
        assert len(state.visible_free_zones()) == 9

    def test_element_tile_lookup(self):
        from feynman.visuals.schemas import ShowTextInstruction

        ctx = _make_ctx(plan=None)
        state = ctx.board_manager.active_board.state
        state.scroll_to_tile(2, 3)
        ctx.board_manager.record(
            ShowTextInstruction(text="x", element_id="text-1")
        )
        assert state.element_tile("text-1") == (2, 3)
        assert state.element_tile("nonexistent") is None

    def test_offscreen_summary(self):
        from feynman.visuals.schemas import BoardZone, ShowTextInstruction

        ctx = _make_ctx(plan=None)
        state = ctx.board_manager.active_board.state

        ctx.board_manager.record(
            ShowTextInstruction(text="a", element_id="text-1", zone=BoardZone.TOP_LEFT)
        )
        state.scroll_to_tile(1, 0)
        summary = state.offscreen_summary()
        assert "left" in summary
        assert "1 element" in summary

    def test_scroll_view_is_ephemeral(self):
        from feynman.visuals.schemas import ScrollViewInstruction

        ctx = _make_ctx(plan=None)
        state = ctx.board_manager.active_board.state
        instr = ScrollViewInstruction(target_x=1, target_y=0)
        state.record(instr)
        # Ephemeral — should not be tracked as an element
        assert len(state._elements) == 0


class TestAdvanceNudge:
    """Prompt nudges agent to call advance_concept() promptly."""

    def test_advance_nudge_present_for_active_concept(self):
        plan = _make_plan(3)
        ctx = _make_ctx(plan=plan)
        prompt = build_teaching_prompt(plan, ctx)
        assert "call advance_concept() promptly" in prompt

    def test_advance_nudge_absent_when_lesson_complete(self):
        plan = _make_plan(2)
        ctx = _make_ctx(plan=plan)
        # Complete all concepts
        ctx.advance()
        ctx.advance()
        assert ctx.is_lesson_complete
        prompt = build_teaching_prompt(plan, ctx)
        assert "call advance_concept() promptly" not in prompt

    def test_advance_nudge_absent_without_plan(self):
        ctx = _make_ctx(plan=None)
        prompt = build_teaching_prompt(None, ctx)
        assert "call advance_concept() promptly" not in prompt


class TestBoardRelationshipsInstructions:
    """Board relationships prompt tells agent about relates_to."""

    def test_relates_to_in_plan_prompt(self):
        plan = _make_plan(2)
        ctx = _make_ctx(plan=plan)
        prompt = build_teaching_prompt(plan, ctx)
        assert "relates_to" in prompt
        assert "Board Relationships" in prompt

    def test_relates_to_in_freeform_prompt(self):
        ctx = _make_ctx(plan=None)
        prompt = build_teaching_prompt(None, ctx)
        assert "relates_to" in prompt

    def test_relation_examples_present(self):
        plan = _make_plan(2)
        ctx = _make_ctx(plan=plan)
        prompt = build_teaching_prompt(plan, ctx)
        assert "illustrates" in prompt
        assert "derives_from" in prompt

    def test_board_relationships_constant_content(self):
        assert "relates_to" in BOARD_RELATIONSHIPS_INSTRUCTIONS
        assert "illustrates" in BOARD_RELATIONSHIPS_INSTRUCTIONS
        assert "derives_from" in BOARD_RELATIONSHIPS_INSTRUCTIONS
        assert "compares_with" in BOARD_RELATIONSHIPS_INSTRUCTIONS


class TestHighlightTimingInstructions:
    """Highlight timing is explained in prompt."""

    def test_highlight_timing_guidance_present(self):
        plan = _make_plan(2)
        ctx = _make_ctx(plan=plan)
        prompt = build_teaching_prompt(plan, ctx)
        assert "Highlights fire INSTANTLY" in prompt
