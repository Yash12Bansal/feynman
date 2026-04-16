"""Scenario-Aware Layout Planner — pre-allocates board space for teaching patterns.

When the agent starts a new concept, this module detects the teaching scenario
(concept intro, derivation, problem solving, etc.) and reserves board regions
for the expected visual elements. The Placement Executor uses these reserved
slots as preferred positions, so the board layout follows a coherent pattern
even though the LLM emits visuals one at a time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from feynman.agent.spatial_solver import Rect, SpatialSolver


class TeachingScenario(StrEnum):
    CONCEPT_INTRO = "concept_intro"
    DERIVATION = "derivation"
    PROBLEM_SOLVING = "problem_solving"
    COMPARISON = "comparison"
    SINGLE_FOCUS = "single_focus"
    FREE_FORM = "free_form"


@dataclass
class ScenarioSlot:
    """A reserved area for a planned element in a teaching scenario."""

    role: str  # "main_diagram", "key_equation", "title", etc.
    rect: Rect  # reserved area on the board
    filled: bool = False
    element_id: str = ""


@dataclass
class ScenarioPlan:
    """Pre-allocated layout for a teaching scenario."""

    scenario: TeachingScenario
    slots: list[ScenarioSlot] = field(default_factory=list)

    def next_unfilled(self) -> ScenarioSlot | None:
        for slot in self.slots:
            if not slot.filled:
                return slot
        return None

    def fill_slot(self, role: str, element_id: str) -> None:
        for slot in self.slots:
            if slot.role == role and not slot.filled:
                slot.filled = True
                slot.element_id = element_id
                return

    def status_lines(self) -> list[str]:
        """Render scenario status for prompt inclusion."""
        lines: list[str] = []
        for slot in self.slots:
            if slot.filled:
                lines.append(f"  [x] {slot.role} -- {slot.element_id}")
            else:
                lines.append(f"  [ ] {slot.role} -- (unfilled, space reserved)")
        return lines


# ── Slot-to-instruction-type mapping ───────────────────────

# Each slot role accepts these instruction types.
_SLOT_TYPE_MAP: dict[str, frozenset[str]] = {
    # Concept intro
    "title": frozenset({"show_text"}),
    "main_diagram": frozenset({"draw_design_diagram", "draw_scene", "draw_diagram"}),
    "key_equation": frozenset({"show_equation"}),
    "supporting_text": frozenset({"show_text"}),
    "follow_up": frozenset({"show_text", "show_equation", "show_graph"}),
    # Derivation
    "reference_diagram": frozenset({"draw_design_diagram", "draw_scene", "draw_diagram"}),
    "starting_equation": frozenset({"show_equation"}),
    "steps": frozenset({"step_equation"}),
    "annotations": frozenset({"show_text", "show_equation"}),
    "result": frozenset({"show_equation", "show_text"}),
    # Problem solving
    "given_find": frozenset({"show_text"}),
    "diagram": frozenset({"draw_design_diagram", "draw_scene", "draw_diagram"}),
    "solution_steps": frozenset({"step_equation", "show_equation"}),
    "answer": frozenset({"show_text", "show_equation"}),
    # Comparison
    "case_a_title": frozenset({"show_text"}),
    "case_b_title": frozenset({"show_text"}),
    "case_a_visual": frozenset({"draw_design_diagram", "draw_scene", "draw_diagram"}),
    "case_b_visual": frozenset({"draw_design_diagram", "draw_scene", "draw_diagram"}),
    "shared_insight": frozenset({"show_text", "show_equation"}),
    # Single focus
    "main_equation": frozenset({"show_equation"}),
    "annotation": frozenset({"show_text", "show_equation"}),
}


def match_slot(
    plan: ScenarioPlan, instruction_type: str,
) -> ScenarioSlot | None:
    """Find the first unfilled slot that accepts this instruction type."""
    for slot in plan.slots:
        if slot.filled:
            continue
        accepted = _SLOT_TYPE_MAP.get(slot.role, frozenset())
        if instruction_type in accepted:
            return slot
    return None


# ── Scenario detection ─────────────────────────────────────


def detect_scenario(
    concept_description: str,
    visual_suggestions: list[str] | None = None,
) -> TeachingScenario:
    """Detect teaching scenario from concept metadata via keyword matching."""
    desc = concept_description.lower()
    suggestions = " ".join(visual_suggestions or []).lower()

    if any(kw in desc for kw in ("derive", "proof", "show that", "step by step")):
        return TeachingScenario.DERIVATION
    if any(kw in desc for kw in ("compare", "contrast", "difference between", "vs")):
        return TeachingScenario.COMPARISON
    if any(kw in desc for kw in ("problem", "solve", "calculate", "find the")):
        return TeachingScenario.PROBLEM_SOLVING
    if any(kw in desc for kw in ("equation", "formula", "law")) and not suggestions:
        return TeachingScenario.SINGLE_FOCUS
    if any(kw in suggestions for kw in ("diagram", "draw", "illustrat", "apparatus")):
        return TeachingScenario.CONCEPT_INTRO

    return TeachingScenario.CONCEPT_INTRO  # default


# ── Layout planning ────────────────────────────────────────

_PAD = 40


def plan_scenario(
    scenario: TeachingScenario,
    solver: SpatialSolver,
) -> ScenarioPlan:
    """Pre-allocate board space for a teaching scenario.

    Returns a ScenarioPlan with reserved slots sized relative to the board.
    The Placement Executor uses these slots as preferred positions.
    """
    w, h = solver.width, solver.height

    if scenario == TeachingScenario.CONCEPT_INTRO:
        return ScenarioPlan(
            scenario=scenario,
            slots=[
                ScenarioSlot("title", Rect(_PAD, _PAD, w * 0.5, 80)),
                ScenarioSlot("main_diagram", Rect(_PAD, 140, w * 0.45, h * 0.55)),
                ScenarioSlot("key_equation", Rect(w * 0.52, 140, w * 0.42, 120)),
                ScenarioSlot("supporting_text", Rect(w * 0.52, 280, w * 0.42, 200)),
                ScenarioSlot("follow_up", Rect(_PAD, h * 0.72, w - 2 * _PAD, h * 0.24)),
            ],
        )

    if scenario == TeachingScenario.DERIVATION:
        return ScenarioPlan(
            scenario=scenario,
            slots=[
                ScenarioSlot("reference_diagram", Rect(_PAD, _PAD, w * 0.25, h * 0.4)),
                ScenarioSlot("starting_equation", Rect(w * 0.3, _PAD, w * 0.4, 80)),
                ScenarioSlot("steps", Rect(w * 0.3, 140, w * 0.4, h * 0.6)),
                ScenarioSlot("annotations", Rect(w * 0.75, 140, w * 0.2, h * 0.5)),
                ScenarioSlot("result", Rect(w * 0.3, h * 0.8, w * 0.4, 100)),
            ],
        )

    if scenario == TeachingScenario.PROBLEM_SOLVING:
        return ScenarioPlan(
            scenario=scenario,
            slots=[
                ScenarioSlot("given_find", Rect(w * 0.6, _PAD, w * 0.35, 150)),
                ScenarioSlot("diagram", Rect(_PAD, _PAD, w * 0.5, h * 0.55)),
                ScenarioSlot("solution_steps", Rect(w * 0.55, 200, w * 0.4, h * 0.45)),
                ScenarioSlot("answer", Rect(w * 0.55, h * 0.7, w * 0.4, 120)),
            ],
        )

    if scenario == TeachingScenario.COMPARISON:
        mid = w * 0.5
        return ScenarioPlan(
            scenario=scenario,
            slots=[
                ScenarioSlot("case_a_title", Rect(_PAD, _PAD, mid - 2 * _PAD, 80)),
                ScenarioSlot("case_b_title", Rect(mid + _PAD, _PAD, mid - 2 * _PAD, 80)),
                ScenarioSlot("case_a_visual", Rect(_PAD, 140, mid - 2 * _PAD, h * 0.45)),
                ScenarioSlot("case_b_visual", Rect(mid + _PAD, 140, mid - 2 * _PAD, h * 0.45)),
                ScenarioSlot("shared_insight", Rect(w * 0.2, h * 0.7, w * 0.6, 150)),
            ],
        )

    if scenario == TeachingScenario.SINGLE_FOCUS:
        return ScenarioPlan(
            scenario=scenario,
            slots=[
                ScenarioSlot("main_equation", Rect(w * 0.15, h * 0.25, w * 0.7, 200)),
                ScenarioSlot("annotation", Rect(w * 0.15, h * 0.6, w * 0.7, 200)),
            ],
        )

    # FREE_FORM — no pre-allocated slots
    return ScenarioPlan(scenario=scenario, slots=[])
