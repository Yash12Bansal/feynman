"""Board state tracker — gives the agent a mental model of what's on screen.

Tracks every visual element placed on the board: its ID, type, zone, and a
human-readable label. Provides a compact summary for inclusion in the LLM
prompt so the agent knows what's where and can make spatial decisions.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from pydantic import BaseModel

from feynman.agent.scene_graph import SceneGraph
from feynman.visuals.schemas import BoardZone, _BaseInstruction

# Instruction type → short prefix for auto-generated element IDs.
_TYPE_PREFIX: dict[str, str] = {
    "show_text": "text",
    "show_equation": "eq",
    "draw_diagram": "diagram",
    "draw_scene": "scene",
    "step_equation": "step",
    "show_graph": "graph",
    "highlight": "hl",
    "annotate": "ann",
}

# Instruction types that are ephemeral — not tracked on the board.
_EPHEMERAL_TYPES = frozenset({"highlight", "annotate", "switch_board"})

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

    def next_id(self, instruction_type: str) -> str:
        """Generate the next auto-ID for a given instruction type.

        Returns IDs like ``text-1``, ``eq-2``, ``diagram-1``.
        """
        prefix = _TYPE_PREFIX.get(instruction_type, instruction_type)
        self._counters[prefix] += 1
        return f"{prefix}-{self._counters[prefix]}"

    def record(self, instruction: _BaseInstruction) -> None:
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
        )

    def remove(self, element_id: str) -> None:
        """Remove a specific element from the board."""
        self._elements.pop(element_id, None)
        self.scene_graph.remove_element(element_id)

    def clear(self) -> None:
        """Wipe the entire board state."""
        self._elements.clear()
        self.scene_graph.clear()

    def zones_in_use(self) -> set[BoardZone]:
        """Return the set of zones that currently have content."""
        return {el.zone for el in self._elements.values() if el.zone is not None}

    def free_zones(self) -> set[BoardZone]:
        """Return zones that don't currently have content."""
        return set(BoardZone) - self.zones_in_use()

    def summary(self) -> str:
        """Compact text summary of the board for LLM prompt inclusion.

        When scene graph has bounds data, produces a richer spatial summary
        with positions, sizes, and relationships. Falls back to zone-only
        format when no bounds are available.
        """
        if not self._elements:
            return "Board is empty."

        # Try scene-graph-enriched summary first.
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

        for el in elements:
            zone_str = f" [{el.zone}]" if el.zone else ""
            lines.append(f"- {el.element_id}: {el.label}{zone_str}")

        return "\n".join(lines)
