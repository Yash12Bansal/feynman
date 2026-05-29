# TODO(DEADCODE): tests parked/dead modules (Group 1/2/3); see docs/engineering/13-redundant-code-audit.md. Safe to delete.
# """Tests for Phase 6 — Scenario-Aware Layout Planner."""

# import pytest

# from feynman.agent.scenario_planner import (
#     ScenarioPlan,
#     ScenarioSlot,
#     TeachingScenario,
#     detect_scenario,
#     match_slot,
#     plan_scenario,
# )
# from feynman.agent.spatial_solver import Rect, SpatialSolver

# # ── detect_scenario ────────────────────────────────────────


# class TestDetectScenario:
#     def test_derivation_keywords(self):
#         assert detect_scenario("Derive the equation for kinetic energy") == TeachingScenario.DERIVATION
#         assert detect_scenario("Proof of the Pythagorean theorem") == TeachingScenario.DERIVATION
#         assert detect_scenario("Show that momentum is conserved") == TeachingScenario.DERIVATION
#         assert detect_scenario("Step by step integration") == TeachingScenario.DERIVATION

#     def test_comparison_keywords(self):
#         assert detect_scenario("Compare mitosis and meiosis") == TeachingScenario.COMPARISON
#         assert detect_scenario("Contrast series vs parallel circuits") == TeachingScenario.COMPARISON
#         assert detect_scenario("Difference between acids and bases") == TeachingScenario.COMPARISON

#     def test_problem_solving_keywords(self):
#         assert detect_scenario("Solve for the acceleration") == TeachingScenario.PROBLEM_SOLVING
#         assert detect_scenario("Calculate the moment of inertia") == TeachingScenario.PROBLEM_SOLVING
#         assert detect_scenario("Find the roots of the polynomial") == TeachingScenario.PROBLEM_SOLVING

#     def test_single_focus_equation_no_visuals(self):
#         assert detect_scenario("Newton's second law equation") == TeachingScenario.SINGLE_FOCUS
#         assert detect_scenario("The quadratic formula") == TeachingScenario.SINGLE_FOCUS

#     def test_single_focus_overridden_by_visual_suggestions(self):
#         # When visual suggestions exist, equation keywords don't trigger SINGLE_FOCUS
#         result = detect_scenario("Newton's second law equation", ["draw a force diagram"])
#         assert result == TeachingScenario.CONCEPT_INTRO

#     def test_concept_intro_from_visual_suggestions(self):
#         assert detect_scenario("Lenses", ["diagram of convex lens"]) == TeachingScenario.CONCEPT_INTRO
#         assert detect_scenario("Cells", ["draw cell structure"]) == TeachingScenario.CONCEPT_INTRO
#         assert detect_scenario("Optics", ["illustration of light"]) == TeachingScenario.CONCEPT_INTRO
#         assert detect_scenario("Lab", ["apparatus setup"]) == TeachingScenario.CONCEPT_INTRO

#     def test_default_is_concept_intro(self):
#         assert detect_scenario("Introduction to thermodynamics") == TeachingScenario.CONCEPT_INTRO
#         assert detect_scenario("What is gravity?") == TeachingScenario.CONCEPT_INTRO

#     def test_priority_derivation_over_others(self):
#         # "derive" wins even if "compare" is also present
#         assert detect_scenario("Derive and compare the two forms") == TeachingScenario.DERIVATION


# # ── plan_scenario ──────────────────────────────────────────


# class TestPlanScenario:
#     @pytest.fixture()
#     def solver(self):
#         return SpatialSolver(1920, 1080)

#     def test_concept_intro_has_5_slots(self, solver):
#         plan = plan_scenario(TeachingScenario.CONCEPT_INTRO, solver)
#         assert plan.scenario == TeachingScenario.CONCEPT_INTRO
#         assert len(plan.slots) == 5
#         roles = [s.role for s in plan.slots]
#         assert roles == ["title", "main_diagram", "key_equation", "supporting_text", "follow_up"]

#     def test_derivation_has_5_slots(self, solver):
#         plan = plan_scenario(TeachingScenario.DERIVATION, solver)
#         assert len(plan.slots) == 5
#         roles = [s.role for s in plan.slots]
#         assert "steps" in roles
#         assert "result" in roles

#     def test_problem_solving_has_4_slots(self, solver):
#         plan = plan_scenario(TeachingScenario.PROBLEM_SOLVING, solver)
#         assert len(plan.slots) == 4
#         roles = [s.role for s in plan.slots]
#         assert "diagram" in roles
#         assert "answer" in roles

#     def test_comparison_has_5_slots(self, solver):
#         plan = plan_scenario(TeachingScenario.COMPARISON, solver)
#         assert len(plan.slots) == 5
#         roles = [s.role for s in plan.slots]
#         assert "case_a_visual" in roles
#         assert "case_b_visual" in roles

#     def test_single_focus_has_2_slots(self, solver):
#         plan = plan_scenario(TeachingScenario.SINGLE_FOCUS, solver)
#         assert len(plan.slots) == 2
#         roles = [s.role for s in plan.slots]
#         assert roles == ["main_equation", "annotation"]

#     def test_free_form_has_no_slots(self, solver):
#         plan = plan_scenario(TeachingScenario.FREE_FORM, solver)
#         assert len(plan.slots) == 0

#     def test_slots_within_board_bounds(self, solver):
#         """All slots must fit within the 1920x1080 board."""
#         for scenario in TeachingScenario:
#             plan = plan_scenario(scenario, solver)
#             for slot in plan.slots:
#                 assert slot.rect.x >= 0, f"{scenario}/{slot.role} x < 0"
#                 assert slot.rect.y >= 0, f"{scenario}/{slot.role} y < 0"
#                 assert slot.rect.right <= 1920, f"{scenario}/{slot.role} right > 1920"
#                 assert slot.rect.bottom <= 1080, f"{scenario}/{slot.role} bottom > 1080"

#     def test_slots_no_overlap_within_scenario(self, solver):
#         """Slots within a single scenario should not overlap each other."""
#         for scenario in TeachingScenario:
#             plan = plan_scenario(scenario, solver)
#             for i, a in enumerate(plan.slots):
#                 for j, b in enumerate(plan.slots):
#                     if i >= j:
#                         continue
#                     assert not a.rect.overlaps(b.rect), (
#                         f"{scenario}: {a.role} overlaps {b.role}"
#                     )

#     def test_slots_start_unfilled(self, solver):
#         plan = plan_scenario(TeachingScenario.CONCEPT_INTRO, solver)
#         for slot in plan.slots:
#             assert not slot.filled
#             assert slot.element_id == ""


# # ── ScenarioPlan methods ───────────────────────────────────


# class TestScenarioPlan:
#     def test_next_unfilled_returns_first(self):
#         plan = ScenarioPlan(
#             scenario=TeachingScenario.CONCEPT_INTRO,
#             slots=[
#                 ScenarioSlot("title", Rect(0, 0, 100, 50)),
#                 ScenarioSlot("main_diagram", Rect(0, 60, 400, 300)),
#             ],
#         )
#         assert plan.next_unfilled().role == "title"

#     def test_next_unfilled_skips_filled(self):
#         plan = ScenarioPlan(
#             scenario=TeachingScenario.CONCEPT_INTRO,
#             slots=[
#                 ScenarioSlot("title", Rect(0, 0, 100, 50), filled=True, element_id="text-1"),
#                 ScenarioSlot("main_diagram", Rect(0, 60, 400, 300)),
#             ],
#         )
#         assert plan.next_unfilled().role == "main_diagram"

#     def test_next_unfilled_returns_none_when_all_filled(self):
#         plan = ScenarioPlan(
#             scenario=TeachingScenario.CONCEPT_INTRO,
#             slots=[
#                 ScenarioSlot("title", Rect(0, 0, 100, 50), filled=True),
#             ],
#         )
#         assert plan.next_unfilled() is None

#     def test_fill_slot(self):
#         plan = ScenarioPlan(
#             scenario=TeachingScenario.CONCEPT_INTRO,
#             slots=[
#                 ScenarioSlot("title", Rect(0, 0, 100, 50)),
#                 ScenarioSlot("main_diagram", Rect(0, 60, 400, 300)),
#             ],
#         )
#         plan.fill_slot("title", "text-1")
#         assert plan.slots[0].filled
#         assert plan.slots[0].element_id == "text-1"
#         assert not plan.slots[1].filled

#     def test_fill_slot_no_double_fill(self):
#         plan = ScenarioPlan(
#             scenario=TeachingScenario.CONCEPT_INTRO,
#             slots=[
#                 ScenarioSlot("title", Rect(0, 0, 100, 50), filled=True, element_id="text-1"),
#             ],
#         )
#         plan.fill_slot("title", "text-2")
#         # First slot stays unchanged — already filled
#         assert plan.slots[0].element_id == "text-1"

#     def test_status_lines(self):
#         plan = ScenarioPlan(
#             scenario=TeachingScenario.CONCEPT_INTRO,
#             slots=[
#                 ScenarioSlot("title", Rect(0, 0, 100, 50), filled=True, element_id="text-1"),
#                 ScenarioSlot("main_diagram", Rect(0, 60, 400, 300)),
#             ],
#         )
#         lines = plan.status_lines()
#         assert len(lines) == 2
#         assert "[x]" in lines[0]
#         assert "text-1" in lines[0]
#         assert "[ ]" in lines[1]
#         assert "unfilled" in lines[1]


# # ── match_slot ─────────────────────────────────────────────


# class TestMatchSlot:
#     def test_equation_matches_key_equation(self):
#         plan = ScenarioPlan(
#             scenario=TeachingScenario.CONCEPT_INTRO,
#             slots=[
#                 ScenarioSlot("title", Rect(0, 0, 100, 50)),
#                 ScenarioSlot("main_diagram", Rect(0, 60, 400, 300)),
#                 ScenarioSlot("key_equation", Rect(500, 60, 300, 100)),
#             ],
#         )
#         slot = match_slot(plan, "show_equation")
#         assert slot is not None
#         assert slot.role == "key_equation"

#     def test_text_matches_title_first(self):
#         plan = ScenarioPlan(
#             scenario=TeachingScenario.CONCEPT_INTRO,
#             slots=[
#                 ScenarioSlot("title", Rect(0, 0, 100, 50)),
#                 ScenarioSlot("supporting_text", Rect(500, 200, 300, 200)),
#             ],
#         )
#         slot = match_slot(plan, "show_text")
#         assert slot is not None
#         assert slot.role == "title"

#     def test_design_diagram_matches_main_diagram(self):
#         plan = ScenarioPlan(
#             scenario=TeachingScenario.CONCEPT_INTRO,
#             slots=[
#                 ScenarioSlot("title", Rect(0, 0, 100, 50)),
#                 ScenarioSlot("main_diagram", Rect(0, 60, 400, 300)),
#             ],
#         )
#         slot = match_slot(plan, "draw_design_diagram")
#         assert slot is not None
#         assert slot.role == "main_diagram"

#     def test_skips_filled_slots(self):
#         plan = ScenarioPlan(
#             scenario=TeachingScenario.CONCEPT_INTRO,
#             slots=[
#                 ScenarioSlot("title", Rect(0, 0, 100, 50), filled=True),
#                 ScenarioSlot("supporting_text", Rect(500, 200, 300, 200)),
#             ],
#         )
#         slot = match_slot(plan, "show_text")
#         assert slot is not None
#         assert slot.role == "supporting_text"

#     def test_returns_none_when_no_match(self):
#         plan = ScenarioPlan(
#             scenario=TeachingScenario.SINGLE_FOCUS,
#             slots=[
#                 ScenarioSlot("main_equation", Rect(200, 200, 500, 200)),
#             ],
#         )
#         # draw_design_diagram doesn't match main_equation
#         assert match_slot(plan, "draw_design_diagram") is None

#     def test_returns_none_for_empty_plan(self):
#         plan = ScenarioPlan(scenario=TeachingScenario.FREE_FORM, slots=[])
#         assert match_slot(plan, "show_text") is None

#     def test_step_equation_matches_steps(self):
#         plan = ScenarioPlan(
#             scenario=TeachingScenario.DERIVATION,
#             slots=[
#                 ScenarioSlot("reference_diagram", Rect(0, 0, 200, 200)),
#                 ScenarioSlot("steps", Rect(300, 100, 400, 500)),
#             ],
#         )
#         slot = match_slot(plan, "step_equation")
#         assert slot is not None
#         assert slot.role == "steps"

#     def test_draw_scene_matches_diagram_slots(self):
#         plan = ScenarioPlan(
#             scenario=TeachingScenario.PROBLEM_SOLVING,
#             slots=[
#                 ScenarioSlot("diagram", Rect(0, 0, 500, 400)),
#             ],
#         )
#         slot = match_slot(plan, "draw_scene")
#         assert slot is not None
#         assert slot.role == "diagram"


# # ── Placement executor integration ─────────────────────────


# class TestPlacementExecutorWithScenario:
#     """Test that resolve_placement uses scenario slots."""

#     def test_scenario_slot_takes_priority(self):
#         from feynman.agent.placement_executor import resolve_placement
#         from feynman.visuals.schemas import ShowTextInstruction

#         solver = SpatialSolver(1920, 1080)
#         plan = plan_scenario(TeachingScenario.CONCEPT_INTRO, solver)

#         instruction = ShowTextInstruction(text="Newton's Laws", title="Title")
#         instruction.element_id = "text-1"

#         resolve_placement(instruction, solver, plan)

#         # Should use the title slot position
#         assert instruction.position_x == plan.slots[0].rect.x
#         assert instruction.position_y == plan.slots[0].rect.y
#         assert plan.slots[0].filled
#         assert plan.slots[0].element_id == "text-1"

#     def test_scenario_slot_fills_sequentially(self):
#         from feynman.agent.placement_executor import resolve_placement
#         from feynman.visuals.schemas import ShowTextInstruction

#         solver = SpatialSolver(1920, 1080)
#         plan = plan_scenario(TeachingScenario.CONCEPT_INTRO, solver)

#         # First text → title slot
#         inst1 = ShowTextInstruction(text="Title Here", title="Title")
#         inst1.element_id = "text-1"
#         resolve_placement(inst1, solver, plan)
#         assert plan.slots[0].filled  # title

#         # Second text → supporting_text slot (title already filled)
#         inst2 = ShowTextInstruction(text="Supporting detail")
#         inst2.element_id = "text-2"
#         resolve_placement(inst2, solver, plan)
#         assert plan.slots[3].filled  # supporting_text
#         assert plan.slots[3].element_id == "text-2"

#     def test_falls_through_when_no_matching_slot(self):
#         from feynman.agent.placement_executor import resolve_placement
#         from feynman.visuals.schemas import ShowGraphInstruction

#         solver = SpatialSolver(1920, 1080)
#         # Single focus has main_equation + annotation — no graph slot
#         plan = plan_scenario(TeachingScenario.SINGLE_FOCUS, solver)

#         instruction = ShowGraphInstruction(
#             title="Sine wave", graph_type="line",
#             series=[{"label": "y=sin(x)", "points": [{"x": 0, "y": 0}]}],
#             x_axis={"label": "x"}, y_axis={"label": "y"},
#         )
#         instruction.element_id = "graph-1"

#         resolve_placement(instruction, solver, plan)

#         # Should still get placed via fallback (solver auto-placement)
#         assert instruction.position_x is not None
#         assert instruction.position_y is not None

#     def test_none_scenario_plan_passes_through(self):
#         from feynman.agent.placement_executor import resolve_placement
#         from feynman.visuals.schemas import ShowTextInstruction

#         solver = SpatialSolver(1920, 1080)
#         instruction = ShowTextInstruction(text="Hello")
#         instruction.element_id = "text-1"

#         # scenario_plan=None → falls through to other strategies
#         resolve_placement(instruction, solver, None)
#         assert instruction.position_x is not None
