"""Board Flow Intelligence — density analysis, scroll/cleanup advice, space reservation.

Composes SpatialSolver geometry with BoardGraph edges and element metadata
to produce actionable board management recommendations for the LLM prompt.

All functions are pure and synchronous — they read state but don't mutate it.
"""

from __future__ import annotations

from dataclasses import dataclass

from feynman.agent.board_graph import BoardGraph
from feynman.agent.spatial_solver import Rect, SpatialSolver


@dataclass(frozen=True)
class FlowAnalysis:
    """Snapshot of the board's visual flow and density."""

    reading_direction: str  # "left_to_right", "top_to_bottom", "mixed"
    density_balance: float  # 0.0 = balanced, 1.0 = all in one quadrant
    weight_center: tuple[float, float]  # area-weighted centroid (x, y)
    crowding_zones: list[str]  # quadrants with density > 0.7
    suggested_action: str  # "continue", "scroll_right", "clear_old", "rebalance"


@dataclass(frozen=True)
class ScrollAdvice:
    """Recommendation to scroll the board for fresh space."""

    direction: str  # "right", "left", "down"
    reason: str
    urgency: float  # 0.0-1.0


@dataclass(frozen=True)
class CleanupCandidate:
    """An element that's safe to erase."""

    element_id: str
    reason: str


@dataclass(frozen=True)
class ReservationHint:
    """Space advisory for an upcoming concept."""

    concept_title: str
    estimated_width: int
    estimated_height: int
    suggested_zone: str


# ── Flow analysis ─────────────────────────────────────────


def analyze_flow(solver: SpatialSolver) -> FlowAnalysis:
    """Analyze the board's visual flow, density balance, and health."""
    occupied = solver.occupied
    if not occupied:
        return FlowAnalysis(
            reading_direction="left_to_right",
            density_balance=0.0,
            weight_center=(solver.width / 2, solver.height / 2),
            crowding_zones=[],
            suggested_action="continue",
        )

    # Reading direction — compare X vs Y progression in reading order.
    order = solver.reading_order()
    direction = _detect_direction(occupied, order)

    # Density balance — variance of quadrant densities, normalized to 0-1.
    density = solver.density_by_quadrant()
    values = list(density.values())
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    # Max variance is 0.1875 (all content in one quadrant: mean=0.25, var=3*0.0625).
    balance = min(variance / 0.1875, 1.0)

    # Weight center — area-weighted centroid.
    total_area = sum(r.area for r in occupied.values())
    cx = sum(r.center_x * r.area for r in occupied.values()) / total_area
    cy = sum(r.center_y * r.area for r in occupied.values()) / total_area

    # Crowding zones.
    crowding = [name for name, pct in density.items() if pct > 0.7]

    # Suggested action.
    free_pct = solver.free_space_percentage()
    if free_pct > 0.5:
        action = "continue"
    elif free_pct < 0.2:
        action = "scroll_right"
    elif len(crowding) >= 2:
        action = "rebalance"
    else:
        action = "continue"

    return FlowAnalysis(
        reading_direction=direction,
        density_balance=round(balance, 2),
        weight_center=(round(cx), round(cy)),
        crowding_zones=crowding,
        suggested_action=action,
    )


def _detect_direction(
    occupied: dict[str, Rect],
    order: list[str],
) -> str:
    """Detect dominant reading direction from element positions."""
    if len(order) < 2:
        return "left_to_right"

    x_advances = 0
    y_advances = 0
    for i in range(1, len(order)):
        prev = occupied[order[i - 1]]
        curr = occupied[order[i]]
        dx = abs(curr.center_x - prev.center_x)
        dy = abs(curr.center_y - prev.center_y)
        if dx > dy:
            x_advances += 1
        elif dy > dx:
            y_advances += 1

    total = x_advances + y_advances
    if total == 0:
        return "mixed"
    if x_advances / total > 0.6:
        return "left_to_right"
    if y_advances / total > 0.6:
        return "top_to_bottom"
    return "mixed"


# ── Scroll advice ─────────────────────────────────────────


def advise_scroll(
    solver: SpatialSolver,
    board_elements: dict[str, object],
) -> ScrollAdvice | None:
    """Recommend scrolling when the board is getting full.

    Returns None when there's plenty of room (>35% free).
    """
    free_pct = solver.free_space_percentage()
    if free_pct > 0.35:
        return None

    occupied = solver.occupied

    # Find the latest element to know where active content is.
    latest_id: str | None = None
    latest_step = -1
    for eid, el in board_elements.items():
        step = getattr(el, "created_at", 0)
        if step > latest_step:
            latest_step = step
            latest_id = eid

    # Determine direction — prefer right (L→R flow).
    direction = "right"
    if latest_id and latest_id in occupied:
        latest_rect = occupied[latest_id]
        # If latest content is already on the right side and top has space,
        # suggest down instead.
        if latest_rect.center_x > solver.width * 0.7:
            density = solver.density_by_quadrant()
            bottom_density = (
                density.get("bottom-left", 0) + density.get("bottom-right", 0)
            ) / 2
            if bottom_density < 0.3:
                direction = "down"

    # Urgency: 0.3 at 35% free, scales to 1.0 at 5% free.
    urgency = min(1.0, max(0.3, 1.0 - (free_pct - 0.05) / 0.30))

    full_pct = round((1.0 - free_pct) * 100)
    reason = f"Board is {full_pct}% full — scroll {direction} for fresh space."

    return ScrollAdvice(direction=direction, reason=reason, urgency=round(urgency, 1))


# ── Cleanup suggestions ──────────────────────────────────


def suggest_cleanup(
    board_elements: dict[str, object],
    board_graph: BoardGraph,
    current_concept_index: int,
) -> list[CleanupCandidate]:
    """Identify elements safe to erase.

    Conservative: only targets elements from 2+ concepts ago that have
    no active relationship edges and aren't cluster anchors.
    """
    candidates: list[tuple[int, str, str]] = []  # (created_at, eid, reason)

    for eid, el in board_elements.items():
        concept_idx = getattr(el, "concept_index", None)
        if concept_idx is None:
            continue
        # Keep current and previous concept.
        if concept_idx >= current_concept_index - 1:
            continue
        # Skip elements with active graph edges.
        if board_graph.get_edges(eid):
            continue

        concept_title = getattr(el, "concept_title", "unknown")
        created = getattr(el, "created_at", 0)
        reason = f"from completed concept '{concept_title}', no active edges"
        candidates.append((created, eid, reason))

    # Oldest first.
    candidates.sort(key=lambda t: t[0])

    return [
        CleanupCandidate(element_id=eid, reason=reason)
        for _, eid, reason in candidates[:3]
    ]


# ── Space reservation ────────────────────────────────────


def reserve_for_upcoming(
    solver: SpatialSolver,
    upcoming: list[tuple[str, str | None]],
) -> list[ReservationHint]:
    """Estimate space needed for upcoming concepts.

    *upcoming* is a list of ``(concept_title, visual_hint)`` pairs.
    Returns advisory hints — nothing is actually blocked.
    """
    if not upcoming:
        return []

    # Don't reserve if board is already too full.
    if solver.free_space_percentage() < 0.2:
        return []

    hints: list[ReservationHint] = []
    largest = solver.largest_free_region()
    if not largest:
        return []

    for title, visual_hint in upcoming[:2]:
        # Estimate size based on visual hint.
        hint_lower = (visual_hint or "").lower()
        if any(kw in hint_lower for kw in ("diagram", "illustrat", "draw", "scene")):
            est_w, est_h = 500, 400
        else:
            est_w, est_h = 400, 200

        # Check if it fits in the largest free region.
        if largest.width < est_w or largest.height < est_h:
            continue

        zone = SpatialSolver._nearest_zone(largest.center_x, largest.center_y)
        hints.append(
            ReservationHint(
                concept_title=title,
                estimated_width=est_w,
                estimated_height=est_h,
                suggested_zone=zone,
            )
        )

    return hints
