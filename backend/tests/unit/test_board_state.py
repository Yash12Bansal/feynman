"""Tests for BoardState tracker — agent's mental model of the board."""

from feynman.agent.board_state import (
    BoardElement,
    BoardState,
    _extract_label,
)
from feynman.agent.scene_graph import BoundsReportElement, BoundsReportPayload
from feynman.visuals.schemas import (
    AnnotateInstruction,
    AnnotationAction,
    BoardZone,
    ClearInstruction,
    DrawDiagramInstruction,
    HighlightInstruction,
    ShowEquationInstruction,
    ShowGraphInstruction,
    ShowTextInstruction,
    StepEquationInstruction,
    SyncMode,
)

# ── BoardElement ─────────────────────────────────────────────


class TestBoardElement:
    def test_construction(self) -> None:
        el = BoardElement(element_id="eq-1", type="show_equation", label="F = ma")
        assert el.element_id == "eq-1"
        assert el.type == "show_equation"
        assert el.label == "F = ma"
        assert el.zone is None
        assert el.created_at == 0

    def test_with_zone(self) -> None:
        el = BoardElement(
            element_id="text-1",
            type="show_text",
            zone=BoardZone.TOP_LEFT,
            label="Title",
            created_at=3,
        )
        assert el.zone == BoardZone.TOP_LEFT
        assert el.created_at == 3


# ── next_id ──────────────────────────────────────────────────


class TestNextId:
    def test_sequential_ids(self) -> None:
        bs = BoardState()
        assert bs.next_id("show_text") == "text-1"
        assert bs.next_id("show_text") == "text-2"
        assert bs.next_id("show_text") == "text-3"

    def test_different_types_independent(self) -> None:
        bs = BoardState()
        assert bs.next_id("show_text") == "text-1"
        assert bs.next_id("show_equation") == "eq-1"
        assert bs.next_id("draw_diagram") == "diagram-1"
        assert bs.next_id("show_text") == "text-2"

    def test_all_prefix_mappings(self) -> None:
        bs = BoardState()
        assert bs.next_id("show_text") == "text-1"
        assert bs.next_id("show_equation") == "eq-1"
        assert bs.next_id("draw_diagram") == "diagram-1"
        assert bs.next_id("step_equation") == "step-1"
        assert bs.next_id("show_graph") == "graph-1"
        assert bs.next_id("highlight") == "hl-1"

    def test_unknown_type_uses_type_as_prefix(self) -> None:
        bs = BoardState()
        assert bs.next_id("custom_type") == "custom_type-1"


# ── record ───────────────────────────────────────────────────


class TestRecord:
    def test_records_text_instruction(self) -> None:
        bs = BoardState()
        instr = ShowTextInstruction(text="Hello world", element_id="text-1")
        bs.record(instr)
        assert "text-1" in bs._elements
        assert bs._elements["text-1"].label == "Hello world"

    def test_records_equation_with_label(self) -> None:
        bs = BoardState()
        instr = ShowEquationInstruction(latex="E = mc^2", label="Einstein", element_id="eq-1")
        bs.record(instr)
        assert bs._elements["eq-1"].label == "Einstein"

    def test_records_with_zone(self) -> None:
        bs = BoardState()
        instr = ShowTextInstruction(
            text="Top left text",
            element_id="text-1",
            zone=BoardZone.TOP_LEFT,
        )
        bs.record(instr)
        assert bs._elements["text-1"].zone == BoardZone.TOP_LEFT

    def test_skips_ephemeral_highlight(self) -> None:
        bs = BoardState()
        instr = HighlightInstruction(target_id="eq-1", element_id="hl-1")
        bs.record(instr)
        assert len(bs._elements) == 0

    def test_skips_ephemeral_annotate(self) -> None:
        bs = BoardState()
        instr = AnnotateInstruction(
            action=AnnotationAction.CIRCLE,
            target_id="eq-1",
            element_id="ann-1",
        )
        bs.record(instr)
        assert len(bs._elements) == 0

    def test_skips_instruction_without_element_id(self) -> None:
        bs = BoardState()
        instr = ShowTextInstruction(text="No ID")
        bs.record(instr)
        assert len(bs._elements) == 0

    def test_clear_all(self) -> None:
        bs = BoardState()
        bs.record(ShowTextInstruction(text="A", element_id="text-1"))
        bs.record(ShowTextInstruction(text="B", element_id="text-2"))
        assert len(bs._elements) == 2

        bs.record(ClearInstruction())
        assert len(bs._elements) == 0

    def test_clear_target(self) -> None:
        bs = BoardState()
        bs.record(ShowTextInstruction(text="A", element_id="text-1"))
        bs.record(ShowTextInstruction(text="B", element_id="text-2"))

        bs.record(ClearInstruction(target_id="text-1"))
        assert "text-1" not in bs._elements
        assert "text-2" in bs._elements

    def test_clear_nonexistent_target_silent(self) -> None:
        bs = BoardState()
        bs.record(ClearInstruction(target_id="does-not-exist"))
        # Should not raise
        assert len(bs._elements) == 0

    def test_step_counter_increments(self) -> None:
        bs = BoardState()
        bs.record(ShowTextInstruction(text="A", element_id="text-1"))
        bs.record(ShowTextInstruction(text="B", element_id="text-2"))
        assert bs._elements["text-1"].created_at == 1
        assert bs._elements["text-2"].created_at == 2

    def test_overwrite_existing_element(self) -> None:
        bs = BoardState()
        bs.record(ShowTextInstruction(text="Old", element_id="text-1"))
        bs.record(ShowTextInstruction(text="New", element_id="text-1"))
        assert bs._elements["text-1"].label == "New"
        assert len(bs._elements) == 1


# ── remove / clear ───────────────────────────────────────────


class TestRemoveAndClear:
    def test_remove(self) -> None:
        bs = BoardState()
        bs.record(ShowTextInstruction(text="A", element_id="text-1"))
        bs.remove("text-1")
        assert len(bs._elements) == 0

    def test_remove_nonexistent_silent(self) -> None:
        bs = BoardState()
        bs.remove("nope")  # Should not raise

    def test_clear(self) -> None:
        bs = BoardState()
        bs.record(ShowTextInstruction(text="A", element_id="text-1"))
        bs.record(ShowEquationInstruction(latex="x=1", element_id="eq-1"))
        bs.clear()
        assert len(bs._elements) == 0


# ── zones_in_use / free_zones ────────────────────────────────


class TestZones:
    def test_empty_board(self) -> None:
        bs = BoardState()
        assert bs.zones_in_use() == set()
        assert bs.free_zones() == set(BoardZone)

    def test_zones_tracked(self) -> None:
        bs = BoardState()
        bs.record(ShowTextInstruction(text="A", element_id="text-1", zone=BoardZone.TOP_LEFT))
        bs.record(ShowTextInstruction(text="B", element_id="text-2", zone=BoardZone.CENTER_CENTER))
        assert bs.zones_in_use() == {BoardZone.TOP_LEFT, BoardZone.CENTER_CENTER}
        assert BoardZone.TOP_LEFT not in bs.free_zones()
        assert BoardZone.BOTTOM_RIGHT in bs.free_zones()

    def test_none_zone_not_tracked(self) -> None:
        bs = BoardState()
        bs.record(ShowTextInstruction(text="A", element_id="text-1"))
        assert bs.zones_in_use() == set()

    def test_zone_freed_after_remove(self) -> None:
        bs = BoardState()
        bs.record(ShowTextInstruction(text="A", element_id="text-1", zone=BoardZone.TOP_LEFT))
        assert BoardZone.TOP_LEFT in bs.zones_in_use()
        bs.remove("text-1")
        assert BoardZone.TOP_LEFT not in bs.zones_in_use()


# ── summary ──────────────────────────────────────────────────


class TestSummary:
    def test_empty_board(self) -> None:
        bs = BoardState()
        assert bs.summary() == "Board is empty."

    def test_single_element(self) -> None:
        bs = BoardState()
        bs.record(ShowTextInstruction(text="Hello", element_id="text-1"))
        s = bs.summary()
        assert "text-1" in s
        assert "Hello" in s

    def test_zone_shown_in_summary(self) -> None:
        bs = BoardState()
        bs.record(
            ShowTextInstruction(
                text="Hello",
                element_id="text-1",
                zone=BoardZone.TOP_LEFT,
            )
        )
        s = bs.summary()
        assert "top-left" in s

    def test_truncation_with_many_elements(self) -> None:
        bs = BoardState()
        for i in range(25):
            bs.record(ShowTextInstruction(text=f"Item {i}", element_id=f"text-{i}"))
        s = bs.summary()
        assert "earlier elements not shown" in s
        # Should show the latest 15
        assert "text-24" in s
        assert "text-10" in s
        # Should not show the oldest ones individually
        assert "text-0:" not in s

    def test_order_is_creation_order(self) -> None:
        bs = BoardState()
        bs.record(ShowTextInstruction(text="First", element_id="text-1"))
        bs.record(ShowEquationInstruction(latex="x=1", element_id="eq-1"))
        lines = bs.summary().split("\n")
        # text-1 should appear before eq-1
        text_idx = next(i for i, line in enumerate(lines) if "text-1" in line)
        eq_idx = next(i for i, line in enumerate(lines) if "eq-1" in line)
        assert text_idx < eq_idx


# ── _extract_label ───────────────────────────────────────────


class TestExtractLabel:
    def test_label_field_priority(self) -> None:
        instr = ShowEquationInstruction(latex="E=mc^2", label="Einstein")
        assert _extract_label(instr) == "Einstein"

    def test_title_fallback(self) -> None:
        instr = DrawDiagramInstruction(title="Forces", description="Force diagram")
        assert _extract_label(instr) == "Forces"

    def test_text_fallback(self) -> None:
        instr = ShowTextInstruction(text="Key point here")
        assert _extract_label(instr) == "Key point here"

    def test_latex_fallback(self) -> None:
        instr = ShowEquationInstruction(latex="a^2 + b^2 = c^2")
        assert _extract_label(instr) == "a^2 + b^2 = c^2"

    def test_description_fallback(self) -> None:
        instr = DrawDiagramInstruction(description="A force diagram")
        assert _extract_label(instr) == "A force diagram"

    def test_graph_type_fallback(self) -> None:
        instr = ShowGraphInstruction(
            graph_type="line",
            series=[{"label": "", "points": [{"x": 0, "y": 0}]}],
        )
        assert _extract_label(instr) == "line"

    def test_truncation(self) -> None:
        long_text = "A" * 100
        instr = ShowTextInstruction(text=long_text)
        assert len(_extract_label(instr)) == 60

    def test_type_fallback_for_clear(self) -> None:
        instr = ClearInstruction(sync_mode=SyncMode.IMMEDIATE)
        assert _extract_label(instr) == "clear"

    def test_step_equation_title(self) -> None:
        instr = StepEquationInstruction(
            title="Solving for x",
            steps=[{"latex": "2x = 6"}],
        )
        assert _extract_label(instr) == "Solving for x"


# ── SceneGraph integration ─────────────────────────────────────


class TestSceneGraphIntegration:
    def test_summary_uses_scene_graph_when_bounds_available(self) -> None:
        bs = BoardState()
        bs.record(ShowTextInstruction(text="Hello", element_id="text-1", zone=BoardZone.TOP_LEFT))
        # Add bounds to the scene graph.
        bs.scene_graph.update_bounds(
            BoundsReportPayload(
                board_id="b",
                elements=[
                    BoundsReportElement(element_id="text-1", x=100, y=100, width=200, height=40),
                ],
            )
        )
        s = bs.summary()
        # Scene graph summary includes position/size labels, not zone brackets.
        assert "text-1" in s
        # Should NOT be the zone-only format (which uses "[top-left]").
        assert "[top-left]" not in s

    def test_summary_falls_back_to_zone_only_when_empty(self) -> None:
        bs = BoardState()
        bs.record(ShowTextInstruction(text="Hello", element_id="text-1", zone=BoardZone.TOP_LEFT))
        # No scene graph bounds → falls back to zone-only.
        s = bs.summary()
        assert "text-1" in s
        assert "Hello" in s
        assert "[top-left]" in s

    def test_remove_delegates_to_scene_graph(self) -> None:
        bs = BoardState()
        bs.record(ShowTextInstruction(text="Hello", element_id="text-1"))
        bs.scene_graph.update_bounds(
            BoundsReportPayload(
                board_id="b",
                elements=[
                    BoundsReportElement(element_id="text-1", x=10, y=10, width=100, height=40),
                ],
            )
        )
        assert bs.scene_graph.get_bounds("text-1") is not None
        bs.remove("text-1")
        assert bs.scene_graph.get_bounds("text-1") is None

    def test_clear_delegates_to_scene_graph(self) -> None:
        bs = BoardState()
        bs.record(ShowTextInstruction(text="A", element_id="text-1"))
        bs.scene_graph.update_bounds(
            BoundsReportPayload(
                board_id="b",
                elements=[
                    BoundsReportElement(element_id="text-1", x=10, y=10, width=100, height=40),
                ],
            )
        )
        bs.clear()
        assert bs.scene_graph.element_count == 0
