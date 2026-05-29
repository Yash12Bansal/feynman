# TODO(DEADCODE): tests parked/dead modules (Group 1/2/3); see docs/engineering/13-redundant-code-audit.md. Safe to delete.
# """Tests for Board and BoardManager — multi-board lifecycle."""

# from __future__ import annotations

# from uuid import uuid4

# import pytest

# from feynman.agent.board import Board, BoardManager
# from feynman.agent.board_state import BoardState
# from feynman.agent.scene_graph import BoundsReportElement, BoundsReportPayload
# from feynman.visuals.schemas import BoardZone, ShowEquationInstruction, ShowTextInstruction

# # ── Board dataclass ───────────────────────────────────────────


# class TestBoard:
#     def test_construction(self) -> None:
#         branch_id = uuid4()
#         board = Board(id="board-1", label="Newton's Laws", branch_id=branch_id)
#         assert board.id == "board-1"
#         assert board.label == "Newton's Laws"
#         assert board.branch_id == branch_id
#         assert board.parent_id is None
#         assert isinstance(board.state, BoardState)

#     def test_element_count_empty(self) -> None:
#         board = Board(id="board-1", label="Test", branch_id=uuid4())
#         assert board.element_count == 0

#     def test_element_count_after_record(self) -> None:
#         board = Board(id="board-1", label="Test", branch_id=uuid4())
#         instr = ShowTextInstruction(text="Hello", element_id="text-1")
#         board.state.record(instr)
#         assert board.element_count == 1

#     def test_parent_id(self) -> None:
#         board = Board(id="board-2", label="Doubt", branch_id=uuid4(), parent_id="board-1")
#         assert board.parent_id == "board-1"


# # ── BoardManager initialization ──────────────────────────────


# class TestBoardManagerInit:
#     def test_creates_initial_board(self) -> None:
#         bm = BoardManager()
#         assert bm.board_count == 1
#         assert bm.active_id == "board-1"
#         assert bm.active_board.label == "Board 1"

#     def test_custom_initial_label(self) -> None:
#         bm = BoardManager(initial_label="Quadratic Equations")
#         assert bm.active_board.label == "Quadratic Equations"

#     def test_custom_initial_branch_id(self) -> None:
#         branch_id = uuid4()
#         bm = BoardManager(initial_branch_id=branch_id)
#         assert bm.active_board.branch_id == branch_id


# # ── Global ID uniqueness ─────────────────────────────────────


# class TestGlobalIds:
#     def test_next_id_sequential(self) -> None:
#         bm = BoardManager()
#         assert bm.next_id("show_text") == "text-1"
#         assert bm.next_id("show_text") == "text-2"
#         assert bm.next_id("show_equation") == "eq-1"

#     def test_ids_unique_across_boards(self) -> None:
#         """IDs generated on different boards are globally unique."""
#         bm = BoardManager()
#         id1 = bm.next_id("show_text")  # text-1 on board-1
#         assert id1 == "text-1"

#         bm.create_and_switch("Board 2", uuid4())
#         id2 = bm.next_id("show_text")  # text-2 on board-2
#         assert id2 == "text-2"  # NOT text-1 again

#         id3 = bm.next_id("show_equation")  # eq-1
#         assert id3 == "eq-1"


# # ── push_board / pop_board lifecycle ──────────────────────────


# class TestPushPopLifecycle:
#     def test_push_board(self) -> None:
#         bm = BoardManager()
#         branch_id = uuid4()
#         new_board = bm.push_board("Doubt: Friction", branch_id)

#         assert bm.board_count == 2
#         assert bm.active_id == new_board.id
#         assert bm.active_board.label == "Doubt: Friction"
#         assert new_board.parent_id == "board-1"

#     def test_pop_board(self) -> None:
#         bm = BoardManager()
#         bm.push_board("Doubt: Friction", uuid4())
#         assert bm.active_id == "board-2"

#         popped_id = bm.pop_board()
#         assert popped_id == "board-2"
#         assert bm.active_id == "board-1"

#     def test_nested_push_pop(self) -> None:
#         bm = BoardManager()
#         bm.push_board("Doubt 1", uuid4())
#         bm.push_board("Nested Doubt", uuid4())
#         assert bm.active_id == "board-3"

#         bm.pop_board()
#         assert bm.active_id == "board-2"

#         bm.pop_board()
#         assert bm.active_id == "board-1"

#     def test_pop_empty_stack_raises(self) -> None:
#         bm = BoardManager()
#         with pytest.raises(RuntimeError, match="stack is empty"):
#             bm.pop_board()

#     def test_boards_preserved_after_pop(self) -> None:
#         """Popped boards still exist — just no longer active."""
#         bm = BoardManager()
#         bm.push_board("Doubt", uuid4())

#         # Add content to doubt board.
#         instr = ShowTextInstruction(text="Doubt content", element_id="text-1")
#         bm.record(instr)
#         assert bm.active_board.element_count == 1

#         popped_id = bm.pop_board()
#         # Board still accessible.
#         doubt_board = bm.get_board(popped_id)
#         assert doubt_board is not None
#         assert doubt_board.element_count == 1


# # ── create_and_switch (concept advancement) ──────────────────


# class TestCreateAndSwitch:
#     def test_creates_new_board_and_switches(self) -> None:
#         bm = BoardManager()
#         branch_id = uuid4()
#         new_board = bm.create_and_switch("Energy Conservation", branch_id)

#         assert bm.board_count == 2
#         assert bm.active_id == new_board.id
#         assert bm.active_board.label == "Energy Conservation"

#     def test_no_stack_push(self) -> None:
#         """create_and_switch doesn't affect the stack."""
#         bm = BoardManager()
#         bm.create_and_switch("Concept 2", uuid4())

#         # Stack is empty — pop should fail.
#         with pytest.raises(RuntimeError, match="stack is empty"):
#             bm.pop_board()

#     def test_old_board_preserved(self) -> None:
#         bm = BoardManager()
#         # Add content to first board.
#         instr = ShowTextInstruction(text="First", element_id="text-1")
#         bm.record(instr)

#         bm.create_and_switch("Concept 2", uuid4())

#         old_board = bm.get_board("board-1")
#         assert old_board is not None
#         assert old_board.element_count == 1


# # ── switch_to (direct navigation) ────────────────────────────


# class TestSwitchTo:
#     def test_switch_to_existing_board(self) -> None:
#         bm = BoardManager()
#         bm.create_and_switch("Board 2", uuid4())
#         assert bm.active_id == "board-2"

#         bm.switch_to("board-1")
#         assert bm.active_id == "board-1"

#     def test_switch_to_invalid_raises(self) -> None:
#         bm = BoardManager()
#         with pytest.raises(KeyError, match="Board not found"):
#             bm.switch_to("board-999")

#     def test_switch_does_not_affect_stack(self) -> None:
#         bm = BoardManager()
#         bm.push_board("Doubt", uuid4())
#         bm.switch_to("board-1")  # Direct nav, no stack change.

#         # Stack still has one entry — pop should work.
#         bm.switch_to("board-2")  # Go back to doubt board.
#         popped = bm.pop_board()
#         assert popped == "board-2"
#         assert bm.active_id == "board-1"


# # ── Element tracking delegation ──────────────────────────────


# class TestElementDelegation:
#     def test_record_on_active_board(self) -> None:
#         bm = BoardManager()
#         instr = ShowTextInstruction(text="Hello", element_id="text-1")
#         bm.record(instr)

#         assert bm.active_board.element_count == 1
#         assert "text-1" in bm.active_board.state._elements

#     def test_remove_from_active_board(self) -> None:
#         bm = BoardManager()
#         instr = ShowTextInstruction(text="Hello", element_id="text-1")
#         bm.record(instr)
#         bm.remove("text-1")
#         assert bm.active_board.element_count == 0

#     def test_clear_active_board(self) -> None:
#         bm = BoardManager()
#         bm.record(ShowTextInstruction(text="A", element_id="text-1"))
#         bm.record(ShowTextInstruction(text="B", element_id="text-2"))
#         bm.clear()
#         assert bm.active_board.element_count == 0

#     def test_zones_in_use(self) -> None:
#         bm = BoardManager()
#         instr = ShowTextInstruction(text="Hello", element_id="text-1", zone=BoardZone.TOP_LEFT)
#         bm.record(instr)
#         assert BoardZone.TOP_LEFT in bm.zones_in_use()

#     def test_free_zones(self) -> None:
#         bm = BoardManager()
#         instr = ShowTextInstruction(text="Hello", element_id="text-1", zone=BoardZone.TOP_LEFT)
#         bm.record(instr)
#         free = bm.free_zones()
#         assert BoardZone.TOP_LEFT not in free
#         assert BoardZone.CENTER_CENTER in free

#     def test_record_does_not_affect_other_boards(self) -> None:
#         """Recording on the active board leaves other boards untouched."""
#         bm = BoardManager()
#         bm.record(ShowTextInstruction(text="On board 1", element_id="text-1"))

#         bm.create_and_switch("Board 2", uuid4())
#         bm.record(ShowEquationInstruction(latex="E=mc^2", element_id="eq-1"))

#         board1 = bm.get_board("board-1")
#         board2 = bm.get_board("board-2")
#         assert board1 is not None
#         assert board2 is not None
#         assert board1.element_count == 1
#         assert board2.element_count == 1
#         assert "text-1" in board1.state._elements
#         assert "eq-1" in board2.state._elements


# # ── Summary methods ───────────────────────────────────────────


# class TestSummary:
#     def test_summary_empty_board(self) -> None:
#         bm = BoardManager()
#         assert "empty" in bm.summary().lower()

#     def test_summary_with_elements(self) -> None:
#         bm = BoardManager()
#         bm.record(ShowTextInstruction(text="Hello", element_id="text-1"))
#         summary = bm.summary()
#         assert "text-1" in summary

#     def test_boards_summary_single_board(self) -> None:
#         bm = BoardManager()
#         overview = bm.boards_summary()
#         assert "board-1" in overview
#         assert "Board 1" in overview

#     def test_boards_summary_multiple_boards(self) -> None:
#         bm = BoardManager()
#         bm.create_and_switch("Concept 2", uuid4())

#         overview = bm.boards_summary()
#         assert "board-1" in overview
#         assert "board-2" in overview
#         assert "Concept 2" in overview

#     def test_boards_summary_marks_active(self) -> None:
#         bm = BoardManager()
#         bm.create_and_switch("Concept 2", uuid4())

#         overview = bm.boards_summary()
#         lines = overview.split("\n")
#         # Active board (board-2) should have the >> marker.
#         active_line = next(line for line in lines if "board-2" in line)
#         assert ">>" in active_line

#     def test_boards_summary_element_counts(self) -> None:
#         bm = BoardManager()
#         bm.record(ShowTextInstruction(text="A", element_id="text-1"))
#         bm.record(ShowTextInstruction(text="B", element_id="text-2"))

#         bm.create_and_switch("Concept 2", uuid4())
#         bm.record(ShowEquationInstruction(latex="x=1", element_id="eq-1"))

#         overview = bm.boards_summary()
#         assert "2 elements" in overview
#         assert "1 element" in overview


# # ── Context accessors ─────────────────────────────────────────


# class TestAccessors:
#     def test_all_boards_order(self) -> None:
#         bm = BoardManager()
#         bm.create_and_switch("B2", uuid4())
#         bm.create_and_switch("B3", uuid4())

#         boards = bm.all_boards
#         assert len(boards) == 3
#         assert boards[0].id == "board-1"
#         assert boards[1].id == "board-2"
#         assert boards[2].id == "board-3"

#     def test_get_board_existing(self) -> None:
#         bm = BoardManager()
#         board = bm.get_board("board-1")
#         assert board is not None
#         assert board.id == "board-1"

#     def test_get_board_missing(self) -> None:
#         bm = BoardManager()
#         assert bm.get_board("board-999") is None


# # ── Full lifecycle scenario ───────────────────────────────────


# class TestFullLifecycle:
#     def test_teach_doubt_resolve_advance(self) -> None:
#         """Simulates: teach concept 1 → doubt → resolve → advance to concept 2."""
#         bm = BoardManager(initial_label="Newton's First Law")
#         branch_main = uuid4()
#         bm.active_board.branch_id = branch_main  # type: ignore[misc]

#         # Teach on board 1.
#         bm.record(ShowTextInstruction(text="Inertia", element_id="text-1"))
#         assert bm.active_board.element_count == 1

#         # Student doubt — push board.
#         branch_doubt = uuid4()
#         doubt_board = bm.push_board("Doubt: What is inertia?", branch_doubt)
#         assert bm.active_id == doubt_board.id
#         bm.record(ShowTextInstruction(text="Inertia explained", element_id="text-2"))

#         # Resolve doubt — pop board.
#         popped = bm.pop_board()
#         assert popped == doubt_board.id
#         assert bm.active_id == "board-1"
#         assert bm.active_board.element_count == 1  # Board 1 unchanged.

#         # Advance concept — create_and_switch.
#         branch_next = uuid4()
#         next_board = bm.create_and_switch("Newton's Second Law", branch_next)
#         assert bm.active_id == next_board.id
#         assert bm.active_board.element_count == 0  # Fresh board.

#         # All boards preserved.
#         assert bm.board_count == 3
#         assert bm.get_board("board-1") is not None
#         assert bm.get_board(doubt_board.id) is not None
#         assert bm.get_board(next_board.id) is not None


# # ── update_bounds routing ────────────────────────────────────


# class TestUpdateBounds:
#     def test_routes_to_correct_board(self) -> None:
#         bm = BoardManager()
#         bm.create_and_switch("Board 2", uuid4())
#         report = BoundsReportPayload(
#             board_id="board-1",
#             elements=[
#                 BoundsReportElement(element_id="text-1", x=10, y=20, width=100, height=50),
#             ],
#         )
#         bm.update_bounds("board-1", report)
#         board1 = bm.get_board("board-1")
#         assert board1 is not None
#         assert board1.state.scene_graph.get_bounds("text-1") is not None
#         # Active board (board-2) should not be affected.
#         assert bm.active_board.state.scene_graph.get_bounds("text-1") is None

#     def test_unknown_board_id_silently_ignored(self) -> None:
#         bm = BoardManager()
#         report = BoundsReportPayload(
#             board_id="board-999",
#             elements=[
#                 BoundsReportElement(element_id="x", x=0, y=0, width=10, height=10),
#             ],
#         )
#         bm.update_bounds("board-999", report)  # Should not raise
