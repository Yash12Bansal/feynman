"""Tests for the scene graph spatial model."""

import pytest

from feynman.agent.scene_graph import (
    BOARD_HEIGHT,
    BOARD_WIDTH,
    BoundsReportElement,
    BoundsReportPayload,
    ElementBounds,
    SceneGraph,
    SpatialRelation,
    _position_label,
    _size_label,
)

# ── ElementBounds geometry ─────────────────────────────────────


class TestElementBounds:
    def test_center(self):
        eb = ElementBounds("a", x=100, y=200, width=80, height=40)
        assert eb.center_x == 140.0
        assert eb.center_y == 220.0

    def test_right_bottom(self):
        eb = ElementBounds("a", x=100, y=200, width=80, height=40)
        assert eb.right == 180.0
        assert eb.bottom == 240.0

    def test_area(self):
        eb = ElementBounds("a", x=0, y=0, width=100, height=50)
        assert eb.area == 5000.0

    def test_overlaps_true(self):
        a = ElementBounds("a", x=0, y=0, width=100, height=100)
        b = ElementBounds("b", x=50, y=50, width=100, height=100)
        assert a.overlaps(b)
        assert b.overlaps(a)

    def test_overlaps_false_no_intersection(self):
        a = ElementBounds("a", x=0, y=0, width=50, height=50)
        b = ElementBounds("b", x=200, y=200, width=50, height=50)
        assert not a.overlaps(b)
        assert not b.overlaps(a)

    def test_overlaps_edge_touching_is_not_overlap(self):
        a = ElementBounds("a", x=0, y=0, width=100, height=100)
        b = ElementBounds("b", x=100, y=0, width=100, height=100)
        assert not a.overlaps(b)

    def test_frozen(self):
        eb = ElementBounds("a", x=0, y=0, width=10, height=10)
        with pytest.raises(AttributeError):
            eb.x = 99  # type: ignore[misc]


# ── Helpers ────────────────────────────────────────────────────


class TestHelpers:
    def test_size_label_small(self):
        # < 2% of board area
        assert _size_label(1000) == "small"

    def test_size_label_medium(self):
        # 2-8% of board area (1920*1080 = 2,073,600)
        assert _size_label(80_000) == "medium"

    def test_size_label_large(self):
        assert _size_label(200_000) == "large"

    def test_position_label_top_left(self):
        assert _position_label(100, 100) == "top-left"

    def test_position_label_middle_center(self):
        assert _position_label(960, 540) == "middle-center"

    def test_position_label_bottom_right(self):
        assert _position_label(1800, 900) == "bottom-right"


# ── BoundsReportPayload ───────────────────────────────────────


class TestBoundsReportPayload:
    def test_parse_minimal(self):
        p = BoundsReportPayload(board_id="board-1")
        assert p.board_id == "board-1"
        assert p.elements == []

    def test_parse_with_elements(self):
        p = BoundsReportPayload(
            board_id="board-1",
            timestamp=123,
            elements=[
                BoundsReportElement(element_id="eq-1", x=10, y=20, width=100, height=50),
            ],
        )
        assert len(p.elements) == 1
        assert p.elements[0].element_id == "eq-1"


# ── SceneGraph: update/remove/clear ───────────────────────────


class TestSceneGraphMutations:
    def _make_report(
        self, *elements: tuple[str, float, float, float, float]
    ) -> BoundsReportPayload:
        return BoundsReportPayload(
            board_id="board-1",
            elements=[
                BoundsReportElement(element_id=eid, x=x, y=y, width=w, height=h)
                for eid, x, y, w, h in elements
            ],
        )

    def test_update_bounds(self):
        sg = SceneGraph()
        sg.update_bounds(self._make_report(("eq-1", 100, 200, 480, 80)))
        assert sg.element_count == 1
        assert sg.get_bounds("eq-1") is not None

    def test_update_bounds_replaces_all(self):
        sg = SceneGraph()
        sg.update_bounds(self._make_report(("eq-1", 100, 200, 480, 80)))
        sg.update_bounds(self._make_report(("text-1", 0, 0, 200, 40)))
        assert sg.element_count == 1
        assert sg.get_bounds("eq-1") is None
        assert sg.get_bounds("text-1") is not None

    def test_remove_element(self):
        sg = SceneGraph()
        sg.update_bounds(
            self._make_report(("eq-1", 100, 200, 480, 80), ("eq-2", 500, 200, 200, 60))
        )
        sg.remove_element("eq-1")
        assert sg.get_bounds("eq-1") is None
        assert sg.get_bounds("eq-2") is not None

    def test_remove_nonexistent_is_noop(self):
        sg = SceneGraph()
        sg.remove_element("nope")  # Should not raise

    def test_clear(self):
        sg = SceneGraph()
        sg.update_bounds(self._make_report(("eq-1", 100, 200, 480, 80)))
        sg.clear()
        assert sg.element_count == 0


# ── SceneGraph: neighbors ──────────────────────────────────────


class TestNeighbors:
    def _make_sg(self) -> SceneGraph:
        sg = SceneGraph()
        sg.update_bounds(
            BoundsReportPayload(
                board_id="board-1",
                elements=[
                    BoundsReportElement(element_id="a", x=100, y=100, width=100, height=50),
                    BoundsReportElement(
                        element_id="b", x=250, y=100, width=100, height=50
                    ),  # close
                    BoundsReportElement(element_id="c", x=1500, y=800, width=100, height=50),  # far
                ],
            )
        )
        return sg

    def test_finds_close_neighbors(self):
        sg = self._make_sg()
        nbrs = sg.neighbors("a", max_distance=300)
        ids = {eb.element_id for eb in nbrs}
        assert "b" in ids
        assert "c" not in ids

    def test_excludes_self(self):
        sg = self._make_sg()
        nbrs = sg.neighbors("a", max_distance=9999)
        ids = {eb.element_id for eb in nbrs}
        assert "a" not in ids

    def test_missing_target_returns_empty(self):
        sg = self._make_sg()
        assert sg.neighbors("nonexistent") == []


# ── SceneGraph: spatial_relation ───────────────────────────────


class TestSpatialRelation:
    def test_above(self):
        sg = SceneGraph()
        sg.update_bounds(
            BoundsReportPayload(
                board_id="b",
                elements=[
                    BoundsReportElement(element_id="top", x=500, y=100, width=100, height=50),
                    BoundsReportElement(element_id="bot", x=500, y=400, width=100, height=50),
                ],
            )
        )
        # "top" is above "bot" (top has lower y → bot's center_y > top's center_y)
        assert sg.spatial_relation("top", "bot") == SpatialRelation.ABOVE

    def test_below(self):
        sg = SceneGraph()
        sg.update_bounds(
            BoundsReportPayload(
                board_id="b",
                elements=[
                    BoundsReportElement(element_id="top", x=500, y=100, width=100, height=50),
                    BoundsReportElement(element_id="bot", x=500, y=400, width=100, height=50),
                ],
            )
        )
        assert sg.spatial_relation("bot", "top") == SpatialRelation.BELOW

    def test_left_of(self):
        sg = SceneGraph()
        sg.update_bounds(
            BoundsReportPayload(
                board_id="b",
                elements=[
                    BoundsReportElement(element_id="left", x=100, y=500, width=100, height=50),
                    BoundsReportElement(element_id="right", x=800, y=500, width=100, height=50),
                ],
            )
        )
        assert sg.spatial_relation("left", "right") == SpatialRelation.LEFT_OF

    def test_right_of(self):
        sg = SceneGraph()
        sg.update_bounds(
            BoundsReportPayload(
                board_id="b",
                elements=[
                    BoundsReportElement(element_id="left", x=100, y=500, width=100, height=50),
                    BoundsReportElement(element_id="right", x=800, y=500, width=100, height=50),
                ],
            )
        )
        assert sg.spatial_relation("right", "left") == SpatialRelation.RIGHT_OF

    def test_overlapping(self):
        sg = SceneGraph()
        sg.update_bounds(
            BoundsReportPayload(
                board_id="b",
                elements=[
                    BoundsReportElement(element_id="a", x=100, y=100, width=200, height=200),
                    BoundsReportElement(element_id="b", x=150, y=150, width=200, height=200),
                ],
            )
        )
        assert sg.spatial_relation("a", "b") == SpatialRelation.OVERLAPPING

    def test_missing_element_returns_none(self):
        sg = SceneGraph()
        assert sg.spatial_relation("a", "b") is None


# ── SceneGraph: density_summary ────────────────────────────────


class TestDensitySummary:
    def test_empty_board(self):
        sg = SceneGraph()
        d = sg.density_summary()
        assert all(v == 0.0 for v in d.values())

    def test_with_elements(self):
        sg = SceneGraph()
        # Element in top-left quadrant
        sg.update_bounds(
            BoundsReportPayload(
                board_id="b",
                elements=[
                    BoundsReportElement(element_id="a", x=0, y=0, width=200, height=100),
                ],
            )
        )
        d = sg.density_summary()
        assert d["top-left"] > 0
        assert d["bottom-right"] == 0.0


# ── SceneGraph: largest_free_region ────────────────────────────


class TestLargestFreeRegion:
    def test_empty_board_returns_full(self):
        sg = SceneGraph()
        r = sg.largest_free_region()
        assert r is not None
        assert r.width == BOARD_WIDTH
        assert r.height == BOARD_HEIGHT

    def test_with_element(self):
        sg = SceneGraph()
        sg.update_bounds(
            BoundsReportPayload(
                board_id="b",
                elements=[
                    BoundsReportElement(element_id="a", x=500, y=400, width=200, height=100),
                ],
            )
        )
        r = sg.largest_free_region()
        assert r is not None
        # The largest free region should not overlap with the element
        eb = sg.get_bounds("a")
        assert eb is not None
        # Region should be significant
        assert r.area > 100_000


# ── SceneGraph: summary ───────────────────────────────────────


class TestSummary:
    def test_empty_returns_empty_string(self):
        sg = SceneGraph()
        assert sg.summary() == ""

    def test_with_bounds_returns_descriptions(self):
        sg = SceneGraph()
        sg.update_bounds(
            BoundsReportPayload(
                board_id="b",
                elements=[
                    BoundsReportElement(element_id="eq-1", x=640, y=200, width=480, height=80),
                ],
            )
        )
        result = sg.summary()
        assert "eq-1" in result
        assert result != ""

    def test_with_labels(self):
        sg = SceneGraph()
        sg.update_bounds(
            BoundsReportPayload(
                board_id="b",
                elements=[
                    BoundsReportElement(element_id="eq-1", x=640, y=200, width=480, height=80),
                ],
            )
        )

        # Simulate BoardElement with label attribute
        class FakeElement:
            label = "E = mc^2"

        result = sg.summary({"eq-1": FakeElement()})
        assert "E = mc^2" in result

    def test_spatial_relationships_included(self):
        sg = SceneGraph()
        sg.update_bounds(
            BoundsReportPayload(
                board_id="b",
                elements=[
                    BoundsReportElement(element_id="eq-1", x=500, y=100, width=200, height=50),
                    BoundsReportElement(element_id="text-1", x=500, y=400, width=200, height=50),
                ],
            )
        )
        result = sg.summary()
        assert "Spatial relationships:" in result

    def test_open_regions_included(self):
        sg = SceneGraph()
        # Small element in top-left — most quadrants should be open
        sg.update_bounds(
            BoundsReportPayload(
                board_id="b",
                elements=[
                    BoundsReportElement(element_id="a", x=10, y=10, width=50, height=30),
                ],
            )
        )
        result = sg.summary()
        assert "Open regions:" in result
