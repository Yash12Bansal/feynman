"""Board state tracker — gives the agent a mental model of what's on screen.

Tracks every visual element placed on the board: its ID, type, zone, and a
human-readable label. Provides a compact summary for inclusion in the LLM
prompt so the agent knows what's where and can make spatial decisions.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from pydantic import BaseModel

from feynman.agent.board_graph import BoardGraph
from feynman.agent.scenario_planner import ScenarioPlan
from feynman.agent.scene_graph import BoundsReportPayload, SceneGraph
from feynman.agent.spatial_solver import Rect, SpatialSolver
from feynman.visuals.schemas import BoardZone, _BaseInstruction

# Instruction type → short prefix for auto-generated element IDs.
_TYPE_PREFIX: dict[str, str] = {
    "show_text": "text",
    "show_equation": "eq",
    "draw_diagram": "diagram",
    "draw_design_diagram": "design",
    "draw_scene": "scene",
    "step_equation": "step",
    "show_graph": "graph",
    "highlight": "hl",
    "annotate": "ann",
}

# Instruction types that are ephemeral — not tracked on the board.
_EPHEMERAL_TYPES = frozenset({
    "highlight", "annotate", "switch_board", "highlight_walk", "scroll_view",
})

# Max label length kept in board elements.
_MAX_LABEL_LEN = 60

# Summary truncation: show this many most-recent elements when board is large.
_SUMMARY_RECENT = 15
_SUMMARY_THRESHOLD = 20


class BoardElement(BaseModel):
    """A single visual element known to be on the board."""

    element_id: str
    type: str
    zone: BoardZone | None = None
    label: str = ""
    created_at: int = 0
    concept_title: str = ""
    concept_index: int | None = None
    tile_x: int = 0
    tile_y: int = 0


def _extract_label(instruction: _BaseInstruction) -> str:
    """Pull a human-readable label from an instruction, best-effort.

    Priority: explicit label → title → type-specific fallback.
    """
    # Try common fields that many instructions share.
    label = getattr(instruction, "label", "") or ""
    if label:
        return label[:_MAX_LABEL_LEN]

    title = getattr(instruction, "title", "") or ""
    if title:
        return title[:_MAX_LABEL_LEN]

    # Type-specific fallbacks.
    text = getattr(instruction, "text", "") or ""
    if text:
        return text[:_MAX_LABEL_LEN]

    latex = getattr(instruction, "latex", "") or ""
    if latex:
        return latex[:_MAX_LABEL_LEN]

    description = getattr(instruction, "description", "") or ""
    if description:
        return description[:_MAX_LABEL_LEN]

    graph_type = getattr(instruction, "graph_type", "") or ""
    if graph_type:
        return str(graph_type)[:_MAX_LABEL_LEN]

    return instruction.type


@dataclass
class BoardState:
    """Tracks what visual elements are currently on the board.

    Not thread-safe — designed for sequential tool-call processing within
    a single LiveKit agent turn (which is guaranteed sequential).
    """

    _elements: dict[str, BoardElement] = field(default_factory=dict)
    _counters: defaultdict[str, int] = field(default_factory=lambda: defaultdict(int))
    _step: int = 0
    scene_graph: SceneGraph = field(default_factory=SceneGraph)
    board_graph: BoardGraph = field(default_factory=BoardGraph)
    spatial_solver: SpatialSolver = field(default_factory=SpatialSolver)
    scenario_plan: ScenarioPlan | None = None
    _design_specs: dict[str, dict] = field(default_factory=dict)

    # Camera position on the infinite canvas (tile coordinates).
    camera_tile_x: int = 0
    camera_tile_y: int = 0

    def next_id(self, instruction_type: str) -> str:
        """Generate the next auto-ID for a given instruction type.

        Returns IDs like ``text-1``, ``eq-2``, ``diagram-1``.
        """
        prefix = _TYPE_PREFIX.get(instruction_type, instruction_type)
        self._counters[prefix] += 1
        return f"{prefix}-{self._counters[prefix]}"

    def record(
        self,
        instruction: _BaseInstruction,
        concept_title: str = "",
        concept_index: int | None = None,
    ) -> None:
        """Record an instruction's effect on the board.

        - Content instructions (show_text, draw_diagram, etc.) → add element.
        - clear → remove target or wipe all.
        - highlight → skip (ephemeral).
        """
        itype = instruction.type

        if itype in _EPHEMERAL_TYPES:
            return

        if itype == "clear":
            target_id = getattr(instruction, "target_id", None)
            if target_id:
                self._elements.pop(target_id, None)
            else:
                self._elements.clear()
            return

        # Content instruction — must have an element_id by now (set by
        # _publish_visual before calling record).
        eid = instruction.element_id
        if eid is None:
            return

        self._step += 1
        self._elements[eid] = BoardElement(
            element_id=eid,
            type=itype,
            zone=instruction.zone,
            label=_extract_label(instruction),
            created_at=self._step,
            concept_title=concept_title,
            concept_index=concept_index,
            tile_x=self.camera_tile_x,
            tile_y=self.camera_tile_y,
        )

    def store_design_spec(self, element_id: str, spec: dict) -> None:
        """Store a DiagramSpec for a design diagram element."""
        self._design_specs[element_id] = spec

    def get_design_spec(self, element_id: str) -> dict | None:
        """Retrieve a stored DiagramSpec by element ID."""
        return self._design_specs.get(element_id)

    def update_spatial(self, report: BoundsReportPayload) -> None:
        """Update scene graph AND spatial solver from frontend bounds.

        Called when the frontend reports actual rendered dimensions.
        Keeps both spatial models in sync.
        """
        self.scene_graph.update_bounds(report)
        rects: dict[str, Rect] = {}
        for el in report.elements:
            rects[el.element_id] = Rect(el.x, el.y, el.width, el.height)
        self.spatial_solver.update_all(rects)

    def remove(self, element_id: str) -> None:
        """Remove a specific element from the board."""
        self._elements.pop(element_id, None)
        self._design_specs.pop(element_id, None)
        self.scene_graph.remove_element(element_id)
        self.board_graph.remove_element(element_id)
        self.spatial_solver.remove(element_id)

    def clear(self) -> None:
        """Wipe the entire board state."""
        self._elements.clear()
        self._design_specs.clear()
        self.scene_graph.clear()
        self.board_graph.clear()
        self.spatial_solver.clear()
        self.scenario_plan = None

    def zones_in_use(self) -> set[BoardZone]:
        """Return the set of zones that currently have content."""
        return {el.zone for el in self._elements.values() if el.zone is not None}

    def free_zones(self) -> set[BoardZone]:
        """Return zones that don't currently have content."""
        return set(BoardZone) - self.zones_in_use()

    # ── Camera / infinite canvas ─────────────────────────────

    def scroll_to_tile(self, tile_x: int, tile_y: int) -> None:
        """Move the viewport camera to a tile position."""
        self.camera_tile_x = tile_x
        self.camera_tile_y = tile_y

    def visible_elements(self) -> dict[str, BoardElement]:
        """Return elements on the current viewport tile."""
        return {
            eid: el
            for eid, el in self._elements.items()
            if el.tile_x == self.camera_tile_x and el.tile_y == self.camera_tile_y
        }

    def visible_zones_in_use(self) -> set[BoardZone]:
        """Return zones that have content on the current viewport tile."""
        return {
            el.zone
            for el in self.visible_elements().values()
            if el.zone is not None
        }

    def visible_free_zones(self) -> set[BoardZone]:
        """Return zones with no content on the current viewport tile."""
        return set(BoardZone) - self.visible_zones_in_use()

    def offscreen_summary(self) -> str:
        """Describe elements not on the current viewport tile."""
        offscreen: dict[tuple[int, int], list[BoardElement]] = defaultdict(list)
        for el in self._elements.values():
            if el.tile_x != self.camera_tile_x or el.tile_y != self.camera_tile_y:
                offscreen[(el.tile_x, el.tile_y)].append(el)

        if not offscreen:
            return ""

        parts: list[str] = []
        for (tx, ty), elements in sorted(offscreen.items()):
            dx = tx - self.camera_tile_x
            dy = ty - self.camera_tile_y
            dirs: list[str] = []
            if dx < 0:
                dirs.append("left")
            elif dx > 0:
                dirs.append("right")
            if dy < 0:
                dirs.append("above")
            elif dy > 0:
                dirs.append("below")
            direction = "-".join(dirs) if dirs else "here"
            parts.append(
                f"{len(elements)} elements {direction} "
                f"[scroll_board(\"{dirs[0] if dirs else 'right'}\") to revisit]"
            )
        return "; ".join(parts)

    def element_tile(self, element_id: str) -> tuple[int, int] | None:
        """Return the tile coordinates of an element, or None if not found."""
        el = self._elements.get(element_id)
        if el is None:
            return None
        return (el.tile_x, el.tile_y)

    def summary(self) -> str:
        """Compact text summary of the board for LLM prompt inclusion.

        Priority: clustered (board_graph + scene_graph) → spatial (scene_graph)
        → flat zone-only listing.
        """
        if not self._elements:
            return "Board is empty."

        # Try clustered summary (board_graph with semantic relationships).
        clustered = self.board_graph.summary(self._elements, self.scene_graph)
        if clustered:
            return clustered

        # Try scene-graph-enriched summary (spatial data from frontend).
        sg_summary = self.scene_graph.summary(self._elements)
        if sg_summary:
            return sg_summary

        # Fallback: zone-only listing (no bounds data from frontend).
        elements = sorted(self._elements.values(), key=lambda e: e.created_at)

        lines: list[str] = []

        if len(elements) > _SUMMARY_THRESHOLD:
            older_count = len(elements) - _SUMMARY_RECENT
            elements = elements[-_SUMMARY_RECENT:]
            lines.append(f"({older_count} earlier elements not shown)")

        current_concept = ""
        for el in elements:
            if el.concept_title and el.concept_title != current_concept:
                current_concept = el.concept_title
                lines.append(f"\n[{current_concept}]")
            zone_str = f" [{el.zone}]" if el.zone else ""
            lines.append(f"- {el.element_id}: {el.label}{zone_str}")

        return "\n".join(lines)
