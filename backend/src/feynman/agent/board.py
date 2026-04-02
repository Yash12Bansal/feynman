"""Multi-board manager — maps boards to the teaching session tree.

Each concept or doubt branch gets its own board with preserved content.
BoardManager orchestrates creation, switching, and stack-based navigation
that mirrors the branch stack in the teaching state machine.

Key design decisions:
- Global element IDs: counters live on BoardManager, not per-board.
  "eq-1" is unique across ALL boards — prevents LLM confusion.
- BoardState unchanged: existing class stays as-is. Board wraps it.
- Stack mirrors branches: push_board/pop_board parallel push_branch/pop_branch.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from uuid import UUID

from feynman.agent.board_state import _TYPE_PREFIX, BoardState
from feynman.agent.scene_graph import BoundsReportPayload
from feynman.visuals.schemas import BoardZone, _BaseInstruction


@dataclass
class Board:
    """A single board page — wraps a BoardState with metadata."""

    id: str
    label: str
    branch_id: UUID
    state: BoardState = field(default_factory=BoardState)
    parent_id: str | None = None

    @property
    def element_count(self) -> int:
        return len(self.state._elements)


class BoardManager:
    """Orchestrates multiple boards across a teaching session.

    Delegates element tracking to the active board's BoardState, but owns
    the ID counters globally so element IDs are unique across all boards.
    """

    def __init__(
        self, initial_label: str = "Board 1", initial_branch_id: UUID | None = None
    ) -> None:
        self._counter = 1
        self._id_counters: defaultdict[str, int] = defaultdict(int)
        self._boards: dict[str, Board] = {}
        self._stack: list[str] = []

        # Create the initial board.
        board_id = self._make_board_id()
        branch_id = initial_branch_id or UUID(int=0)
        initial_board = Board(
            id=board_id,
            label=initial_label,
            branch_id=branch_id,
        )
        self._boards[board_id] = initial_board
        self._active_id = board_id

    # ── Element tracking (delegate to active board) ───────────

    def next_id(self, instruction_type: str) -> str:
        """Generate a globally unique element ID."""
        prefix = _TYPE_PREFIX.get(instruction_type, instruction_type)
        self._id_counters[prefix] += 1
        return f"{prefix}-{self._id_counters[prefix]}"

    def record(self, instruction: _BaseInstruction) -> None:
        """Record an instruction on the active board."""
        self.active_board.state.record(instruction)

    def remove(self, element_id: str) -> None:
        """Remove a specific element from the active board."""
        self.active_board.state.remove(element_id)

    def clear(self) -> None:
        """Clear all elements from the active board."""
        self.active_board.state.clear()

    def zones_in_use(self) -> set[BoardZone]:
        """Zones occupied on the active board."""
        return self.active_board.state.zones_in_use()

    def free_zones(self) -> set[BoardZone]:
        """Zones available on the active board."""
        return self.active_board.state.free_zones()

    def summary(self) -> str:
        """Active board's element summary."""
        return self.active_board.state.summary()

    def store_design_spec(self, element_id: str, spec: dict) -> None:
        """Store a DiagramSpec on the active board."""
        self.active_board.state.store_design_spec(element_id, spec)

    def get_design_spec(self, element_id: str) -> dict | None:
        """Retrieve a stored DiagramSpec, searching all boards.

        The LLM may reference a diagram on a non-active board (e.g. after
        switching boards), so we search all boards, active first.
        """
        # Check active board first (most common case).
        spec = self.active_board.state.get_design_spec(element_id)
        if spec is not None:
            return spec
        # Search other boards.
        for board in self._boards.values():
            if board.id == self._active_id:
                continue
            spec = board.state.get_design_spec(element_id)
            if spec is not None:
                return spec
        return None

    def update_bounds(self, board_id: str, report: BoundsReportPayload) -> None:
        """Route a bounds report to the correct board's scene graph."""
        board = self._boards.get(board_id)
        if board is None:
            return  # Silently ignore unknown board IDs
        board.state.scene_graph.update_bounds(report)

    # ── Board lifecycle ───────────────────────────────────────

    def create_board(self, label: str, branch_id: UUID) -> Board:
        """Create a new board without switching to it."""
        board_id = self._make_board_id()
        board = Board(
            id=board_id,
            label=label,
            branch_id=branch_id,
            parent_id=self._active_id,
        )
        self._boards[board_id] = board
        return board

    def push_board(self, label: str, branch_id: UUID) -> Board:
        """Create a new board and push the current one onto the return stack.

        Used for doubt branches — mirrors push_branch in the state machine.
        """
        self._stack.append(self._active_id)
        board = self.create_board(label, branch_id)
        self._active_id = board.id
        return board

    def pop_board(self) -> str:
        """Pop the stack and return to the previous board.

        Used when resolving doubts — mirrors pop_branch.
        Returns the board ID that was popped (the doubt board).
        """
        if not self._stack:
            msg = "Cannot pop board — stack is empty"
            raise RuntimeError(msg)
        popped_id = self._active_id
        self._active_id = self._stack.pop()
        return popped_id

    def create_and_switch(self, label: str, branch_id: UUID) -> Board:
        """Create a new board and switch to it without pushing to stack.

        Used for concept advancement — old board stays accessible but
        we don't need to return to it via stack.
        """
        board = self.create_board(label, branch_id)
        self._active_id = board.id
        return board

    def switch_to(self, board_id: str) -> None:
        """Switch to a specific board by ID. No stack changes."""
        if board_id not in self._boards:
            msg = f"Board not found: {board_id}"
            raise KeyError(msg)
        self._active_id = board_id

    # ── Context accessors ─────────────────────────────────────

    @property
    def active_board(self) -> Board:
        return self._boards[self._active_id]

    @property
    def active_id(self) -> str:
        return self._active_id

    @property
    def board_count(self) -> int:
        return len(self._boards)

    @property
    def all_boards(self) -> list[Board]:
        """All boards in creation order."""
        return list(self._boards.values())

    def get_board(self, board_id: str) -> Board | None:
        return self._boards.get(board_id)

    def boards_summary(self) -> str:
        """Overview of all boards for the LLM prompt."""
        lines: list[str] = []
        for board in self._boards.values():
            marker = ">> " if board.id == self._active_id else "   "
            count = board.element_count
            elements_str = f"{count} element{'s' if count != 1 else ''}"
            lines.append(f"{marker}{board.id}: {board.label} ({elements_str})")
        return "\n".join(lines)

    # ── Internal ──────────────────────────────────────────────

    def _make_board_id(self) -> str:
        board_id = f"board-{self._counter}"
        self._counter += 1
        return board_id
