"""Placement Executor — resolves spatial intent into exact pixel coordinates.

Takes a visual instruction + SpatialSolver, estimates rendered size,
and stamps position_x/position_y via a 4-strategy fallback chain:

1. PlacementIntent (near + relation) → solver anchored placement
2. Zone → zone center with collision avoidance
3. Auto → solver best-fit in free space
4. Full board → warning, leave unpositioned (frontend zone flex fallback)

Called in _publish_visual() before sending instructions to the frontend.
"""

from __future__ import annotations

import structlog

from feynman.agent.scenario_planner import ScenarioPlan, match_slot
from feynman.agent.size_estimator import (
    SizeEstimate,
    estimate_design_diagram_size,
    estimate_diagram_size,
    estimate_equation_size,
    estimate_graph_size,
    estimate_scene_size,
    estimate_step_equation_size,
    estimate_text_size,
)
from feynman.agent.spatial_solver import (
    ELEMENT_PADDING,
    Rect,
    SpatialRelation,
    SpatialSolver,
)
from feynman.visuals.schemas import BoardZone, PlacementIntent, _BaseInstruction

logger = structlog.get_logger()

# ── Constants ────────────────────────────────────────────────

# Only renderable content types need spatial placement.
_PLACEABLE_TYPES = frozenset({
    "show_text",
    "show_equation",
    "step_equation",
    "draw_diagram",
    "draw_design_diagram",
    "show_graph",
    "draw_scene",
})

# Map string relation names → SpatialRelation enum.
_RELATION_MAP: dict[str, SpatialRelation] = {
    "right_of": SpatialRelation.RIGHT_OF,
    "left_of": SpatialRelation.LEFT_OF,
    "below": SpatialRelation.BELOW,
    "above": SpatialRelation.ABOVE,
    "centered": SpatialRelation.CENTERED,
}

# Zone centers for zone → coordinate conversion (1920x1080 board).
_ZONE_CENTERS: dict[str, tuple[float, float]] = {
    "top-left": (240, 150),
    "top-center": (960, 150),
    "top-right": (1680, 150),
    "center-left": (240, 540),
    "center-center": (960, 540),
    "center-right": (1680, 540),
    "bottom-left": (240, 900),
    "bottom-center": (960, 900),
    "bottom-right": (1680, 900),
}


# ── Public API ───────────────────────────────────────────────


def resolve_placement(
    instruction: _BaseInstruction,
    solver: SpatialSolver,
    scenario_plan: ScenarioPlan | None = None,
) -> None:
    """Resolve placement intent into exact position coordinates.

    Modifies the instruction in-place, setting position_x and position_y.
    Falls back gracefully: scenario slot → intent → zone → solver best-fit → warning.
    """
    # Guard: skip non-renderable types
    if instruction.type not in _PLACEABLE_TYPES:
        return

    # Guard: already positioned
    if instruction.position_x is not None and instruction.position_y is not None:
        return

    size = _estimate_size(instruction)

    # Strategy 0: Scenario slot — pre-reserved position from teaching pattern
    if scenario_plan:
        slot = match_slot(scenario_plan, instruction.type)
        if slot:
            instruction.position_x = slot.rect.x
            instruction.position_y = slot.rect.y
            slot.filled = True
            slot.element_id = instruction.element_id or ""
            logger.debug(
                "placement.resolved",
                strategy="scenario",
                element_id=instruction.element_id,
                slot_role=slot.role,
                x=slot.rect.x,
                y=slot.rect.y,
            )
            return

    # Strategy 1: PlacementIntent with near + relation
    # Only fire when there's an actual anchor element — size_hint alone
    # should not bypass zone strategy.
    if instruction.placement and instruction.placement.near:
        result = _resolve_intent(instruction.placement, size, solver)
        if result:
            instruction.position_x = result.x
            instruction.position_y = result.y
            logger.debug(
                "placement.resolved",
                strategy="intent",
                element_id=instruction.element_id,
                x=result.x,
                y=result.y,
                reason=result.reason,
            )
            return

    # Strategy 2: Zone → coordinate with collision avoidance
    if instruction.zone:
        result = _resolve_zone(instruction.zone, size, solver)
        if result:
            instruction.position_x = result.x
            instruction.position_y = result.y
            logger.debug(
                "placement.resolved",
                strategy="zone",
                element_id=instruction.element_id,
                zone=instruction.zone.value,
                x=result.x,
                y=result.y,
            )
            return

    # Strategy 3: Solver picks best available position
    result = solver.find_placement(size.width, size.height)
    if result:
        instruction.position_x = result.x
        instruction.position_y = result.y
        logger.debug(
            "placement.resolved",
            strategy="auto",
            element_id=instruction.element_id,
            x=result.x,
            y=result.y,
            reason=result.reason,
        )
        return

    # Strategy 4: Board full — leave unpositioned (frontend zone flex fallback)
    logger.warning(
        "placement.no_space",
        element_id=instruction.element_id,
        type=instruction.type,
    )


# ── Internal helpers ─────────────────────────────────────────


def _resolve_intent(
    intent: PlacementIntent,
    size: SizeEstimate,
    solver: SpatialSolver,
) -> "PlacementResult | None":
    """Resolve a PlacementIntent to exact coordinates."""
    from feynman.agent.spatial_solver import PlacementResult  # noqa: F811

    relation = _RELATION_MAP.get(
        intent.relation or "right_of", SpatialRelation.RIGHT_OF
    )

    if intent.near:
        return solver.find_placement(
            size.width,
            size.height,
            anchor_id=intent.near,
            relation=relation,
        )

    # No anchor — just use solver's best-fit
    return solver.find_placement(size.width, size.height)


def _resolve_zone(
    zone: BoardZone,
    size: SizeEstimate,
    solver: SpatialSolver,
) -> "PlacementResult | None":
    """Convert zone to coordinates using solver for collision avoidance."""
    from feynman.agent.spatial_solver import PlacementResult

    center = _ZONE_CENTERS.get(zone.value)
    if not center:
        return None

    cx, cy = center
    x = cx - size.width / 2
    y = cy - size.height / 2

    # Clamp to board bounds
    x = max(ELEMENT_PADDING, min(x, solver.width - size.width - ELEMENT_PADDING))
    y = max(ELEMENT_PADDING, min(y, solver.height - size.height - ELEMENT_PADDING))

    # Check collisions
    candidate = Rect(x, y, size.width, size.height)
    if not solver.is_area_free(candidate):
        # Zone center blocked — let solver find best position
        return solver.find_placement(size.width, size.height)

    return PlacementResult(
        x=x,
        y=y,
        width=size.width,
        height=size.height,
        confidence=0.8,
        zone_hint=zone.value,
        reason=f"zone {zone.value} center",
    )


def _estimate_size(instruction: _BaseInstruction) -> SizeEstimate:
    """Estimate the rendered size of an instruction.

    Dispatches to type-specific estimators in size_estimator.py.
    """
    itype = instruction.type

    # Use size_hint from placement intent for diagram-like types when available
    size_hint = None
    if instruction.placement and instruction.placement.size_hint:
        size_hint = instruction.placement.size_hint.value

    if itype == "show_equation":
        return estimate_equation_size(getattr(instruction, "latex", "") or "")

    if itype == "show_text":
        return estimate_text_size(
            getattr(instruction, "text", "") or "",
            getattr(instruction, "title", "") or "",
        )

    if itype == "draw_design_diagram":
        # Use spec dimensions when available (most accurate)
        spec = getattr(instruction, "spec", None)
        if spec and isinstance(spec, dict):
            w = spec.get("width")
            h = spec.get("height")
            if w and h:
                return SizeEstimate(width=float(w), height=float(h), confidence=0.9)
        # Fall back to size_hint or description-based estimate
        if size_hint:
            return estimate_diagram_size(size_hint)
        desc = getattr(instruction, "description", "") or ""
        return estimate_design_diagram_size(desc)

    if itype == "draw_diagram":
        if size_hint:
            return estimate_diagram_size(size_hint)
        nodes = getattr(instruction, "nodes", None) or []
        complexity = "large" if len(nodes) > 6 else "medium" if len(nodes) > 3 else "small"
        return estimate_diagram_size(complexity)

    if itype == "draw_scene":
        elements = getattr(instruction, "elements", None) or []
        return estimate_scene_size(len(elements))

    if itype == "step_equation":
        steps = getattr(instruction, "steps", None) or []
        return estimate_step_equation_size(len(steps))

    if itype == "show_graph":
        series = getattr(instruction, "series", None) or []
        return estimate_graph_size(len(series))

    # Default for unknown types
    return SizeEstimate(width=400, height=300, confidence=0.3)
