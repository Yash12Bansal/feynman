"""Tests for BoardGraph — semantic relationship graph of board elements."""

from feynman.agent.board_graph import BoardEdge, BoardGraph, BoardRelation
from feynman.agent.board_state import BoardElement, BoardState
from feynman.visuals.schemas import (
    BoardZone,
    ShowEquationInstruction,
    ShowTextInstruction,
)

# ── BoardRelation ────────────────────────────────────────────


class TestBoardRelation:
    def test_all_values(self) -> None:
        assert BoardRelation.ILLUSTRATES == "illustrates"
        assert BoardRelation.DERIVES_FROM == "derives_from"
        assert BoardRelation.COMPARES_WITH == "compares_with"
        assert BoardRelation.SUPPORTS == "supports"
        assert BoardRelation.ANNOTATES == "annotates"

    def test_from_string(self) -> None:
        assert BoardRelation("illustrates") == BoardRelation.ILLUSTRATES


# ── BoardEdge ────────────────────────────────────────────────


class TestBoardEdge:
    def test_construction(self) -> None:
        edge = BoardEdge(
            source_id="eq-1",
            target_id="design-1",
            relation=BoardRelation.ILLUSTRATES,
        )
        assert edge.source_id == "eq-1"
        assert edge.target_id == "design-1"
        assert edge.relation == BoardRelation.ILLUSTRATES
        assert edge.label == ""

    def test_with_label(self) -> None:
        edge = BoardEdge(
            source_id="step-1",
            target_id="eq-1",
            relation=BoardRelation.DERIVES_FROM,
            label="substitution",
        )
        assert edge.label == "substitution"


# ── BoardGraph: add / remove / clear ────────────────────────


class TestBoardGraphBasics:
    def test_empty_graph(self) -> None:
        g = BoardGraph()
        assert g.edge_count == 0
        assert g.get_edges("eq-1") == []

    def test_add_edge(self) -> None:
        g = BoardGraph()
        g.add_edge("eq-1", "design-1", BoardRelation.ILLUSTRATES)
        assert g.edge_count == 1
        edges = g.get_edges("eq-1")
        assert len(edges) == 1
        assert edges[0].target_id == "design-1"

    def test_add_multiple_edges(self) -> None:
        g = BoardGraph()
        g.add_edge("eq-1", "design-1", BoardRelation.ILLUSTRATES)
        g.add_edge("text-1", "design-1", BoardRelation.SUPPORTS)
        assert g.edge_count == 2
        # design-1 appears in both
        edges = g.get_edges("design-1")
        assert len(edges) == 2

    def test_remove_element(self) -> None:
        g = BoardGraph()
        g.add_edge("eq-1", "design-1", BoardRelation.ILLUSTRATES)
        g.add_edge("text-1", "design-1", BoardRelation.SUPPORTS)
        g.remove_element("design-1")
        assert g.edge_count == 0

    def test_remove_element_partial(self) -> None:
        g = BoardGraph()
        g.add_edge("eq-1", "design-1", BoardRelation.ILLUSTRATES)
        g.add_edge("text-1", "eq-2", BoardRelation.SUPPORTS)
        g.remove_element("eq-1")
        assert g.edge_count == 1
        assert g.get_edges("text-1")[0].target_id == "eq-2"

    def test_remove_nonexistent_silent(self) -> None:
        g = BoardGraph()
        g.add_edge("eq-1", "design-1", BoardRelation.ILLUSTRATES)
        g.remove_element("nope")
        assert g.edge_count == 1

    def test_clear(self) -> None:
        g = BoardGraph()
        g.add_edge("eq-1", "design-1", BoardRelation.ILLUSTRATES)
        g.add_edge("text-1", "design-1", BoardRelation.SUPPORTS)
        g.clear()
        assert g.edge_count == 0


# ── Cluster detection ────────────────────────────────────────


class TestClusterDetection:
    def test_single_element_no_edges(self) -> None:
        g = BoardGraph()
        cluster = g.get_cluster("eq-1")
        assert cluster == {"eq-1"}

    def test_two_connected_elements(self) -> None:
        g = BoardGraph()
        g.add_edge("eq-1", "design-1", BoardRelation.ILLUSTRATES)
        cluster = g.get_cluster("eq-1")
        assert cluster == {"eq-1", "design-1"}
        # Same from the other side.
        assert g.get_cluster("design-1") == {"eq-1", "design-1"}

    def test_transitive_cluster(self) -> None:
        g = BoardGraph()
        g.add_edge("eq-1", "design-1", BoardRelation.ILLUSTRATES)
        g.add_edge("step-1", "eq-1", BoardRelation.DERIVES_FROM)
        g.add_edge("text-1", "design-1", BoardRelation.SUPPORTS)
        cluster = g.get_cluster("step-1")
        assert cluster == {"eq-1", "design-1", "step-1", "text-1"}

    def test_two_separate_clusters(self) -> None:
        g = BoardGraph()
        g.add_edge("eq-1", "design-1", BoardRelation.ILLUSTRATES)
        g.add_edge("eq-2", "design-2", BoardRelation.ILLUSTRATES)
        assert g.get_cluster("eq-1") == {"eq-1", "design-1"}
        assert g.get_cluster("eq-2") == {"eq-2", "design-2"}

    def test_get_clusters_all_components(self) -> None:
        g = BoardGraph()
        g.add_edge("eq-1", "design-1", BoardRelation.ILLUSTRATES)
        g.add_edge("eq-2", "design-2", BoardRelation.ILLUSTRATES)
        all_ids = {"eq-1", "design-1", "eq-2", "design-2", "graph-1"}
        clusters = g.get_clusters(all_ids)
        assert len(clusters) == 3  # two pairs + one singleton
        sizes = sorted(len(c) for c in clusters)
        assert sizes == [1, 2, 2]

    def test_get_clusters_empty(self) -> None:
        g = BoardGraph()
        assert g.get_clusters(set()) == []


# ── Anchor detection ─────────────────────────────────────────


def _make_el(eid: str, etype: str, created: int = 0) -> BoardElement:
    return BoardElement(element_id=eid, type=etype, created_at=created)


class TestAnchorDetection:
    def test_prefers_diagram_type(self) -> None:
        g = BoardGraph()
        g.add_edge("eq-1", "design-1", BoardRelation.ILLUSTRATES)
        elements = {
            "eq-1": _make_el("eq-1", "show_equation", 2),
            "design-1": _make_el("design-1", "draw_design_diagram", 1),
        }
        anchor = g.get_anchor({"eq-1", "design-1"}, elements)
        assert anchor == "design-1"

    def test_prefers_most_incoming(self) -> None:
        g = BoardGraph()
        g.add_edge("eq-1", "design-1", BoardRelation.ILLUSTRATES)
        g.add_edge("text-1", "design-1", BoardRelation.SUPPORTS)
        g.add_edge("step-1", "design-1", BoardRelation.DERIVES_FROM)
        elements = {
            "eq-1": _make_el("eq-1", "show_equation", 2),
            "text-1": _make_el("text-1", "show_text", 3),
            "step-1": _make_el("step-1", "step_equation", 4),
            "design-1": _make_el("design-1", "draw_design_diagram", 1),
        }
        cluster = {"eq-1", "text-1", "step-1", "design-1"}
        anchor = g.get_anchor(cluster, elements)
        assert anchor == "design-1"

    def test_fallback_to_earliest_creation(self) -> None:
        g = BoardGraph()
        g.add_edge("eq-1", "eq-2", BoardRelation.DERIVES_FROM)
        elements = {
            "eq-1": _make_el("eq-1", "show_equation", 1),
            "eq-2": _make_el("eq-2", "show_equation", 2),
        }
        anchor = g.get_anchor({"eq-1", "eq-2"}, elements)
        # eq-2 has 1 incoming, eq-1 has 0 — so eq-2 wins by incoming count.
        assert anchor == "eq-2"

    def test_empty_cluster(self) -> None:
        g = BoardGraph()
        assert g.get_anchor(set(), {}) is None

    def test_scene_type_is_anchor(self) -> None:
        g = BoardGraph()
        g.add_edge("eq-1", "scene-1", BoardRelation.ILLUSTRATES)
        elements = {
            "eq-1": _make_el("eq-1", "show_equation", 2),
            "scene-1": _make_el("scene-1", "draw_scene", 1),
        }
        assert g.get_anchor({"eq-1", "scene-1"}, elements) == "scene-1"

    def test_graph_type_is_anchor(self) -> None:
        g = BoardGraph()
        g.add_edge("text-1", "graph-1", BoardRelation.SUPPORTS)
        elements = {
            "text-1": _make_el("text-1", "show_text", 1),
            "graph-1": _make_el("graph-1", "show_graph", 2),
        }
        assert g.get_anchor({"text-1", "graph-1"}, elements) == "graph-1"


# ── Summary output ───────────────────────────────────────────


class TestSummary:
    def test_empty_no_edges(self) -> None:
        g = BoardGraph()
        assert g.summary({}) == ""

    def test_clustered_summary_format(self) -> None:
        g = BoardGraph()
        g.add_edge("eq-1", "design-1", BoardRelation.ILLUSTRATES)
        g.add_edge("text-1", "design-1", BoardRelation.SUPPORTS)
        elements = {
            "design-1": BoardElement(
                element_id="design-1",
                type="draw_design_diagram",
                label="Free body diagram",
                zone=BoardZone.CENTER_LEFT,
                created_at=1,
            ),
            "eq-1": BoardElement(
                element_id="eq-1",
                type="show_equation",
                label="F = ma",
                zone=BoardZone.CENTER_RIGHT,
                created_at=2,
            ),
            "text-1": BoardElement(
                element_id="text-1",
                type="show_text",
                label="Key insight",
                zone=BoardZone.TOP_CENTER,
                created_at=3,
            ),
        }
        summary = g.summary(elements)
        assert "Cluster" in summary
        assert "anchor: design-1" in summary
        assert "Free body diagram" in summary
        assert "eq-1" in summary
        assert "text-1" in summary
        assert "illustrates" in summary
        assert "supports" in summary

    def test_standalone_elements_shown(self) -> None:
        g = BoardGraph()
        g.add_edge("eq-1", "design-1", BoardRelation.ILLUSTRATES)
        elements = {
            "design-1": BoardElement(
                element_id="design-1", type="draw_design_diagram",
                label="Diagram", created_at=1,
            ),
            "eq-1": BoardElement(
                element_id="eq-1", type="show_equation",
                label="E=mc2", created_at=2,
            ),
            "graph-1": BoardElement(
                element_id="graph-1", type="show_graph",
                label="Plot", zone=BoardZone.BOTTOM_RIGHT, created_at=3,
            ),
        }
        summary = g.summary(elements)
        assert "Standalone" in summary
        assert "graph-1" in summary

    def test_multi_cluster_summary(self) -> None:
        g = BoardGraph()
        g.add_edge("eq-1", "design-1", BoardRelation.ILLUSTRATES)
        g.add_edge("eq-2", "design-2", BoardRelation.ILLUSTRATES)
        elements = {
            "design-1": _make_el("design-1", "draw_design_diagram", 1),
            "eq-1": _make_el("eq-1", "show_equation", 2),
            "design-2": _make_el("design-2", "draw_design_diagram", 3),
            "eq-2": _make_el("eq-2", "show_equation", 4),
        }
        summary = g.summary(elements)
        # Should have two Cluster: lines.
        assert summary.count("Cluster") >= 2


# ── BoardState integration ───────────────────────────────────


class TestBoardStateIntegration:
    def test_board_state_has_board_graph(self) -> None:
        bs = BoardState()
        assert isinstance(bs.board_graph, BoardGraph)

    def test_remove_cascades_to_board_graph(self) -> None:
        bs = BoardState()
        bs.record(ShowTextInstruction(text="A", element_id="text-1"))
        bs.record(ShowEquationInstruction(latex="x=1", element_id="eq-1"))
        bs.board_graph.add_edge("eq-1", "text-1", BoardRelation.ILLUSTRATES)
        assert bs.board_graph.edge_count == 1
        bs.remove("eq-1")
        assert bs.board_graph.edge_count == 0

    def test_clear_cascades_to_board_graph(self) -> None:
        bs = BoardState()
        bs.record(ShowTextInstruction(text="A", element_id="text-1"))
        bs.record(ShowEquationInstruction(latex="x=1", element_id="eq-1"))
        bs.board_graph.add_edge("eq-1", "text-1", BoardRelation.ILLUSTRATES)
        bs.clear()
        assert bs.board_graph.edge_count == 0

    def test_summary_prefers_clustered(self) -> None:
        """When board_graph has edges, summary should use clustered format."""
        bs = BoardState()
        bs.record(
            ShowTextInstruction(
                text="Key point", element_id="text-1", zone=BoardZone.TOP_CENTER
            )
        )
        bs.record(
            ShowEquationInstruction(
                latex="F=ma", label="Newton", element_id="eq-1",
                zone=BoardZone.CENTER_RIGHT,
            )
        )
        bs.board_graph.add_edge("eq-1", "text-1", BoardRelation.ILLUSTRATES)
        summary = bs.summary()
        assert "Cluster" in summary
        assert "anchor" in summary

    def test_summary_falls_back_to_flat_when_no_edges(self) -> None:
        bs = BoardState()
        bs.record(ShowTextInstruction(text="Hello", element_id="text-1"))
        summary = bs.summary()
        # No edges → no cluster → flat format.
        assert "text-1" in summary
        assert "Cluster" not in summary
