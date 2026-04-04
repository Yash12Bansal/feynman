"""Tests for Phase 7: Concept Context + ConceptGraph Board Hints."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from feynman.agent.board import BoardManager
from feynman.agent.board_graph import BoardGraph, BoardRelation
from feynman.agent.board_state import BoardElement, BoardState
from feynman.agent.lesson_plan import ConceptNode, LessonPlan
from feynman.agent.prompts import _build_graph_context, build_teaching_prompt
from feynman.agent.state_machine import TeachingStateMachine
from feynman.agent.teaching_context import TeachingContext
from feynman.common.types import Subject
from feynman.visuals.schemas import ShowEquationInstruction, ShowTextInstruction

# ── Helpers ──────────────────────────────────────────────────


def _make_concept(title: str) -> ConceptNode:
    return ConceptNode(
        title=title,
        description=f"Teach {title}",
        key_points=["point 1"],
        visual_suggestions=["diagram"],
    )


def _make_plan(titles: list[str] | None = None) -> LessonPlan:
    titles = titles or ["Newton's Laws", "Conservation of Energy"]
    return LessonPlan(
        topic="Physics",
        subject=Subject.PHYSICS,
        grade_level="Grade 10",
        objective="Teach physics",
        concepts=[_make_concept(t) for t in titles],
    )


def _make_ctx(plan: LessonPlan | None = None) -> TeachingContext:
    session_id = uuid4()
    sm = TeachingStateMachine(session_id=session_id)
    return TeachingContext(
        session_id=session_id,
        state_machine=sm,
        lesson_plan=plan,
    )


# ── Mock ConceptGraph (duck-typed, matches data_pre_compute models) ──


@dataclass
class _MockRelation:
    value: str


@dataclass
class _MockEdge:
    source_id: str
    target_id: str
    relation: _MockRelation
    label: str = ""


@dataclass
class _MockNode:
    node_id: str
    topic_name: str
    summary: str = ""


@dataclass
class _MockConceptGraph:
    nodes: dict[str, _MockNode] = field(default_factory=dict)
    _edges: list[_MockEdge] = field(default_factory=list)

    def get_related_edges(self, node_id: str) -> list[_MockEdge]:
        return [
            e for e in self._edges if e.source_id == node_id or e.target_id == node_id
        ]


def _make_graph() -> _MockConceptGraph:
    """Graph: Newton's Laws -[prerequisite]-> Conservation of Energy -[leads_to]-> Momentum."""
    n1 = _MockNode("n1", "Newton's Laws")
    n2 = _MockNode("n2", "Conservation of Energy")
    n3 = _MockNode("n3", "Momentum")
    return _MockConceptGraph(
        nodes={"n1": n1, "n2": n2, "n3": n3},
        _edges=[
            _MockEdge("n1", "n2", _MockRelation("prerequisite")),
            _MockEdge("n2", "n3", _MockRelation("leads_to")),
            _MockEdge("n3", "n1", _MockRelation("example_of")),
        ],
    )


# ── BoardElement concept fields ──────────────────────────────


class TestBoardElementConceptFields:
    def test_defaults(self) -> None:
        el = BoardElement(element_id="eq-1", type="show_equation")
        assert el.concept_title == ""
        assert el.concept_index is None

    def test_set_explicitly(self) -> None:
        el = BoardElement(
            element_id="eq-1",
            type="show_equation",
            concept_title="Newton's Laws",
            concept_index=0,
        )
        assert el.concept_title == "Newton's Laws"
        assert el.concept_index == 0


# ── BoardState.record() concept stamping ─────────────────────


class TestRecordConceptStamping:
    def test_stamps_concept(self) -> None:
        bs = BoardState()
        instr = ShowTextInstruction(text="Key formula", element_id="text-1")
        bs.record(instr, concept_title="Forces", concept_index=2)
        el = bs._elements["text-1"]
        assert el.concept_title == "Forces"
        assert el.concept_index == 2

    def test_defaults_without_concept(self) -> None:
        bs = BoardState()
        instr = ShowTextInstruction(text="Hello", element_id="text-1")
        bs.record(instr)
        el = bs._elements["text-1"]
        assert el.concept_title == ""
        assert el.concept_index is None


# ── BoardManager.record() passthrough ────────────────────────


class TestBoardManagerPassthrough:
    def test_passes_concept_to_board_state(self) -> None:
        bm = BoardManager()
        instr = ShowEquationInstruction(
            latex="F=ma", label="Newton", element_id="eq-1"
        )
        bm.record(instr, concept_title="Newton's Second Law", concept_index=1)
        el = bm.active_board.state._elements["eq-1"]
        assert el.concept_title == "Newton's Second Law"
        assert el.concept_index == 1


# ── Flat summary with concept grouping ───────────────────────


class TestFlatSummaryConceptGrouping:
    def test_groups_by_concept(self) -> None:
        bs = BoardState()
        bs.record(
            ShowTextInstruction(text="A", element_id="text-1"),
            concept_title="Forces",
            concept_index=0,
        )
        bs.record(
            ShowEquationInstruction(latex="F=ma", element_id="eq-1"),
            concept_title="Forces",
            concept_index=0,
        )
        bs.record(
            ShowTextInstruction(text="B", element_id="text-2"),
            concept_title="Energy",
            concept_index=1,
        )
        summary = bs.summary()
        assert "[Forces]" in summary
        assert "[Energy]" in summary
        # Forces header appears before Energy header
        assert summary.index("[Forces]") < summary.index("[Energy]")

    def test_no_grouping_without_concept(self) -> None:
        """Elements without concept_title don't get concept headers."""
        bs = BoardState()
        bs.record(ShowTextInstruction(text="A", element_id="text-1"))
        bs.record(ShowTextInstruction(text="B", element_id="text-2"))
        summary = bs.summary()
        assert "[" not in summary  # No concept headers


# ── Clustered summary with concept label ─────────────────────


class TestClusteredSummaryConceptLabel:
    def test_concept_in_cluster_header(self) -> None:
        g = BoardGraph()
        g.add_edge("eq-1", "design-1", BoardRelation.ILLUSTRATES)
        elements = {
            "design-1": BoardElement(
                element_id="design-1",
                type="draw_design_diagram",
                label="FBD",
                created_at=1,
                concept_title="Newton's Laws",
            ),
            "eq-1": BoardElement(
                element_id="eq-1",
                type="show_equation",
                label="F=ma",
                created_at=2,
                concept_title="Newton's Laws",
            ),
        }
        summary = g.summary(elements)
        assert "Cluster" in summary
        assert "(Newton's Laws)" in summary

    def test_no_concept_no_parenthetical(self) -> None:
        g = BoardGraph()
        g.add_edge("eq-1", "design-1", BoardRelation.ILLUSTRATES)
        elements = {
            "design-1": BoardElement(
                element_id="design-1",
                type="draw_design_diagram",
                label="FBD",
                created_at=1,
            ),
            "eq-1": BoardElement(
                element_id="eq-1",
                type="show_equation",
                label="F=ma",
                created_at=2,
            ),
        }
        summary = g.summary(elements)
        assert "Cluster" in summary
        # No concept parenthetical — concept_title defaults to ""
        assert "()" not in summary


# ── current_graph_node property ──────────────────────────────


class TestCurrentGraphNode:
    def test_no_graph(self) -> None:
        ctx = _make_ctx(plan=_make_plan())
        assert ctx.current_graph_node is None

    def test_no_plan(self) -> None:
        ctx = _make_ctx(plan=None)
        ctx.concept_graph = _make_graph()
        assert ctx.current_graph_node is None

    def test_matches_by_title(self) -> None:
        plan = _make_plan(["Newton's Laws", "Conservation of Energy"])
        ctx = _make_ctx(plan=plan)
        ctx.concept_graph = _make_graph()
        node = ctx.current_graph_node
        assert node is not None
        assert node.node_id == "n1"
        assert node.topic_name == "Newton's Laws"

    def test_matches_after_advance(self) -> None:
        plan = _make_plan(["Newton's Laws", "Conservation of Energy"])
        ctx = _make_ctx(plan=plan)
        ctx.concept_graph = _make_graph()
        ctx.advance()
        node = ctx.current_graph_node
        assert node is not None
        assert node.node_id == "n2"

    def test_no_match_returns_none(self) -> None:
        plan = _make_plan(["Unrelated Topic XYZ"])
        ctx = _make_ctx(plan=plan)
        ctx.concept_graph = _make_graph()
        assert ctx.current_graph_node is None


# ── _build_graph_context ─────────────────────────────────────


class TestBuildGraphContext:
    def test_no_graph(self) -> None:
        ctx = _make_ctx(plan=_make_plan())
        assert _build_graph_context(ctx) == ""

    def test_prerequisite_hint(self) -> None:
        plan = _make_plan(["Newton's Laws", "Conservation of Energy"])
        ctx = _make_ctx(plan=plan)
        ctx.concept_graph = _make_graph()
        # At concept 0 (Newton's Laws), edge n1→n2 is prerequisite
        result = _build_graph_context(ctx)
        assert "Cross-concept connections" in result
        # Newton's Laws is source of prerequisite edge to Conservation of Energy
        assert "Conservation of Energy" in result

    def test_leads_to_hint(self) -> None:
        plan = _make_plan(["Newton's Laws", "Conservation of Energy"])
        ctx = _make_ctx(plan=plan)
        ctx.concept_graph = _make_graph()
        ctx.advance()  # Now at Conservation of Energy (n2)
        result = _build_graph_context(ctx)
        assert "leads to" in result.lower()
        assert "Momentum" in result

    def test_included_in_prompt(self) -> None:
        plan = _make_plan(["Newton's Laws", "Conservation of Energy"])
        ctx = _make_ctx(plan=plan)
        ctx.concept_graph = _make_graph()
        prompt = build_teaching_prompt(plan, ctx)
        assert "Cross-concept connections" in prompt
