"""Tests for the anticipation engine — classification, matching, cache, graph conversion."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from feynman.agent.anticipation import (
    AnticipationEngine,
    _build_prompt_from_graph_node,
    _extract_visual_prompts_from_plan,
    _jaccard,
    _meaningful_tokens,
    _needs_design_agent,
)
from feynman.agent.lesson_plan import ConceptNode, LessonPlan, lesson_plan_from_graph
from feynman.agent.session_audit import SessionAudit
from feynman.common.types import Subject

# ── Helpers ───────────────────────────────────────────────


def _make_concept(title: str = "Test Concept", **kwargs) -> ConceptNode:
    return ConceptNode(
        title=title,
        description=kwargs.get("description", "Teach the basics"),
        key_points=kwargs.get("key_points", ["point 1", "point 2"]),
        visual_suggestions=kwargs.get("visual_suggestions", ["show equation"]),
        estimated_minutes=kwargs.get("estimated_minutes", 5.0),
    )


def _make_plan(num_concepts: int = 3, visual_suggestions: list[str] | None = None) -> LessonPlan:
    concepts = []
    for i in range(num_concepts):
        vs = visual_suggestions if visual_suggestions else ["show equation"]
        concepts.append(_make_concept(f"Concept {i + 1}", visual_suggestions=vs))
    return LessonPlan(
        topic="Newton's Laws of Motion",
        subject=Subject.PHYSICS,
        grade_level="Grade 11",
        objective="Understand Newton's three laws",
        concepts=concepts,
    )


# ── Mock ConceptGraph structures ──────────────────────────


class _MockRelationType:
    def __init__(self, value: str):
        self.value = value


@dataclass
class _MockGraphNode:
    node_id: str
    topic_name: str
    summary: str
    content: str = ""
    level: int = 0
    order: int = 0
    page_start: int = 0
    page_end: int = 0
    children_ids: list[str] = field(default_factory=list)
    parent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class _MockGraphEdge:
    source_id: str
    target_id: str
    relation: _MockRelationType
    label: str = ""


class _MockConceptGraph:
    def __init__(self, title: str, nodes: list[_MockGraphNode], edges: list[_MockGraphEdge] | None = None):
        self.chapter_title = title
        self.nodes = {n.node_id: n for n in nodes}
        self.edges = edges or []

    def get_teaching_order(self) -> list[_MockGraphNode]:
        return sorted(self.nodes.values(), key=lambda n: n.order)

    def get_children(self, node_id: str) -> list[_MockGraphNode]:
        node = self.nodes.get(node_id)
        if not node:
            return []
        return [self.nodes[cid] for cid in node.children_ids if cid in self.nodes]

    def get_related_edges(self, node_id: str) -> list[_MockGraphEdge]:
        return [e for e in self.edges if e.source_id == node_id or e.target_id == node_id]


def _make_graph() -> _MockConceptGraph:
    nodes = [
        _MockGraphNode(
            node_id="n1",
            topic_name="Newton's First Law",
            summary="Newton's first law states that an object at rest stays at rest, and an object in motion stays in motion unless acted upon by a net external force. Draw a diagram showing a block on a frictionless surface with no net force.",
            order=0,
        ),
        _MockGraphNode(
            node_id="n2",
            topic_name="Newton's Second Law",
            summary="Newton's second law relates force, mass, and acceleration via F = ma. Show a free body diagram of a mass with applied force and resulting acceleration vector.",
            order=1,
        ),
        _MockGraphNode(
            node_id="n3",
            topic_name="Newton's Third Law",
            summary="For every action there is an equal and opposite reaction. Illustrate two blocks pushing against each other with action-reaction force pairs.",
            order=2,
        ),
    ]
    edges = [
        _MockGraphEdge("n1", "n2", _MockRelationType("prerequisite")),
        _MockGraphEdge("n2", "n3", _MockRelationType("leads_to")),
    ]
    return _MockConceptGraph("Newton's Laws of Motion", nodes, edges)


# ── Classification tests ──────────────────────────────────


class TestNeedsDesignAgent:
    def test_diagram_keywords(self):
        assert _needs_design_agent("Draw a free body diagram") is True
        assert _needs_design_agent("Show the apparatus setup") is True
        assert _needs_design_agent("Illustrate the ray diagram for a convex lens") is True
        assert _needs_design_agent("Sketch the circuit diagram") is True

    def test_fast_tool_keywords(self):
        assert _needs_design_agent("Show the equation F = ma") is False
        assert _needs_design_agent("Derive the formula for kinetic energy") is False
        assert _needs_design_agent("Plot a graph of velocity vs time") is False
        assert _needs_design_agent("Draw a flowchart of the process") is False

    def test_compound_design_wins_over_fast(self):
        # Specific design phrases override fast keywords.
        assert _needs_design_agent("Draw a ray diagram showing the equation") is True
        assert _needs_design_agent("Free body diagram with force equation") is True
        assert _needs_design_agent("Circuit diagram of the setup") is True

    def test_generic_design_loses_to_fast(self):
        # Generic "draw/diagram" defers to specific fast-tool content types.
        assert _needs_design_agent("Draw a diagram showing the equation derivation") is False
        assert _needs_design_agent("Draw a graph of velocity") is False

    def test_ambiguous_returns_false(self):
        assert _needs_design_agent("Explain Newton's second law clearly") is False
        assert _needs_design_agent("Discuss the concept in detail") is False


# ── Tokenization and matching tests ───────────────────────


class TestTokenization:
    def test_meaningful_tokens(self):
        tokens = _meaningful_tokens("Draw a free body diagram of forces")
        assert "free" in tokens
        assert "body" in tokens
        assert "forces" in tokens
        # Stop words removed.
        assert "a" not in tokens
        assert "of" not in tokens

    def test_jaccard_identical(self):
        a = {"free", "body", "diagram"}
        assert _jaccard(a, a) == 1.0

    def test_jaccard_disjoint(self):
        assert _jaccard({"a", "b"}, {"c", "d"}) == 0.0

    def test_jaccard_partial(self):
        a = {"free", "body", "diagram", "forces"}
        b = {"free", "body", "diagram", "incline"}
        score = _jaccard(a, b)
        assert 0.5 < score < 1.0  # 3/5 = 0.6

    def test_jaccard_empty(self):
        assert _jaccard(set(), {"a"}) == 0.0
        assert _jaccard(set(), set()) == 0.0


# ── Visual prompt extraction tests ────────────────────────


class TestExtractVisualPrompts:
    def test_design_suggestion_extracted(self):
        concept = _make_concept(
            "Forces",
            description="Understand different types of forces",
            visual_suggestions=["Draw a free body diagram", "show equation F = ma"],
        )
        prompts = _extract_visual_prompts_from_plan(concept)
        assert len(prompts) == 1  # only the diagram one
        assert "free body diagram" in prompts[0]
        assert "Forces" in prompts[0]  # concept title enrichment

    def test_no_design_suggestions(self):
        concept = _make_concept(
            "Algebra",
            visual_suggestions=["show equation", "plot graph"],
        )
        prompts = _extract_visual_prompts_from_plan(concept)
        assert len(prompts) == 0


class TestBuildPromptFromGraphNode:
    def test_spatial_node_returns_prompt(self):
        graph = _make_graph()
        node = graph.nodes["n2"]  # "Show a free body diagram..."
        prompt = _build_prompt_from_graph_node(node, graph)
        assert prompt is not None
        assert "Newton's Second Law" in prompt
        assert "free body diagram" in prompt.lower() or "force" in prompt.lower()

    def test_prerequisite_context_included(self):
        graph = _make_graph()
        node = graph.nodes["n2"]
        prompt = _build_prompt_from_graph_node(node, graph)
        assert prompt is not None
        assert "Newton's First Law" in prompt  # prereq from edge n1→n2

    def test_node_with_summary_returns_prompt(self):
        """Every node with a summary gets a prompt — the design agent can
        always create a useful teaching diagram from rich curriculum text."""
        graph = _MockConceptGraph(
            "Math",
            [_MockGraphNode("m1", "Algebraic Simplification", "Simplify expressions by combining like terms and factoring polynomials.")],
        )
        prompt = _build_prompt_from_graph_node(graph.nodes["m1"], graph)
        assert prompt is not None
        assert "Algebraic Simplification" in prompt


# ── AnticipationEngine tests ──────────────────────────────


class TestAnticipationEngine:
    def test_init(self):
        engine = AnticipationEngine()
        assert engine.cache_size == 0

    @pytest.mark.asyncio
    async def test_warm_from_plan(self):
        plan = _make_plan(
            3,
            visual_suggestions=["Draw a detailed diagram of the forces"],
        )
        engine = AnticipationEngine()

        fake_spec = {"title": "Forces", "elements": [{"id": "e1"}]}
        with patch(
            "feynman.agent.design_bridge.generate_design_diagram",
            new_callable=AsyncMock,
            return_value=fake_spec,
        ):
            await engine.warm_from_plan(plan, start=0, count=2)

        # Should have cached specs for concepts 0 and 1.
        assert engine.cache_size == 2
        assert (0, 0) in engine._cache
        assert (1, 0) in engine._cache

    @pytest.mark.asyncio
    async def test_warm_from_graph(self):
        graph = _make_graph()
        # Build a plan whose concept titles match graph node topic names.
        plan = LessonPlan(
            topic="Newton's Laws of Motion",
            objective="Understand Newton's laws",
            concepts=[
                _make_concept("Newton's First Law"),
                _make_concept("Newton's Second Law"),
                _make_concept("Newton's Third Law"),
            ],
        )
        engine = AnticipationEngine()

        fake_spec = {"title": "Test", "elements": []}
        with patch(
            "feynman.agent.design_bridge.generate_design_diagram",
            new_callable=AsyncMock,
            return_value=fake_spec,
        ):
            await engine.warm_from_graph(graph, plan, start=0, count=3)

        # All 3 graph nodes have visual content → should generate for each.
        assert engine.cache_size == 3

    @pytest.mark.asyncio
    async def test_match_exact_concept(self):
        engine = AnticipationEngine()
        engine._cache[(1, 0)] = {"title": "FBD", "elements": []}
        engine._prompts[(1, 0)] = "Draw a free body diagram of forces on inclined plane"

        result = engine.match(
            "Draw free body diagram showing forces on an inclined plane",
            concept_index=1,
        )
        assert result is not None
        assert result["title"] == "FBD"

    @pytest.mark.asyncio
    async def test_match_adjacent_concept(self):
        engine = AnticipationEngine()
        engine._cache[(2, 0)] = {"title": "Wave", "elements": []}
        engine._prompts[(2, 0)] = "Draw interference pattern for double slit experiment"

        # Agent asks at concept 1, but cache is at concept 2 (±1 search).
        result = engine.match(
            "Draw double slit interference pattern",
            concept_index=1,
        )
        assert result is not None

    def test_match_no_hit(self):
        """No cache entry for concept 5 and Jaccard too low for ±1 adjacent."""
        engine = AnticipationEngine()
        engine._cache[(0, 0)] = {"title": "X", "elements": []}
        engine._prompts[(0, 0)] = "Draw a circuit diagram with resistors"

        result = engine.match(
            "Draw a free body diagram of gravitational forces",
            concept_index=5,  # far from concept 0 — no direct hit, no adjacent
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_skips_already_cached(self):
        engine = AnticipationEngine()
        # Pre-fill cache for concept 0.
        engine._cache[(0, 0)] = {"title": "Pre-existing", "elements": []}
        engine._prompts[(0, 0)] = "already cached prompt"

        plan = _make_plan(
            2,
            visual_suggestions=["Draw a detailed diagram of the setup"],
        )
        call_count = 0
        original_spec = {"title": "New", "elements": []}

        async def fake_gen(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return original_spec

        with patch(
            "feynman.agent.design_bridge.generate_design_diagram",
            side_effect=fake_gen,
        ):
            await engine.warm_from_plan(plan, start=0, count=2)

        # Only concept 1 should have been generated (concept 0 was cached).
        assert call_count == 1
        assert engine._cache[(0, 0)]["title"] == "Pre-existing"  # unchanged

    @pytest.mark.asyncio
    async def test_generation_failure_doesnt_crash(self):
        plan = _make_plan(
            2,
            visual_suggestions=["Draw a diagram of the apparatus"],
        )
        engine = AnticipationEngine()

        with patch(
            "feynman.agent.design_bridge.generate_design_diagram",
            new_callable=AsyncMock,
            side_effect=RuntimeError("API error"),
        ):
            await engine.warm_from_plan(plan, start=0, count=2)

        # Cache should be empty — generation failed but no crash.
        assert engine.cache_size == 0


# ── Session audit integration ─────────────────────────────


class TestAnticipationAudit:
    @pytest.mark.asyncio
    async def test_audit_records_source(self):
        audit = SessionAudit()
        engine = AnticipationEngine(audit=audit)
        plan = _make_plan(1, visual_suggestions=["Draw a diagram"])

        fake_spec = {"title": "T", "elements": []}
        with patch(
            "feynman.agent.design_bridge.generate_design_diagram",
            new_callable=AsyncMock,
            return_value=fake_spec,
        ):
            await engine.warm_from_plan(plan, start=0, count=1)

        assert audit.count("anticipation", "source_plan") == 1
        assert audit.count("anticipation", "pre_generated") == 1

    @pytest.mark.asyncio
    async def test_audit_records_graph_source(self):
        audit = SessionAudit()
        engine = AnticipationEngine(audit=audit)
        plan = _make_plan(3)
        graph = _make_graph()

        fake_spec = {"title": "T", "elements": []}
        with patch(
            "feynman.agent.design_bridge.generate_design_diagram",
            new_callable=AsyncMock,
            return_value=fake_spec,
        ):
            await engine.warm_from_graph(graph, plan, start=0, count=3)

        assert audit.count("anticipation", "source_graph") == 1


# ── Graph → LessonPlan conversion ────────────────────────


class TestLessonPlanFromGraph:
    def test_basic_conversion(self):
        graph = _make_graph()
        plan = lesson_plan_from_graph(graph, grade_level="Grade 11")
        assert plan.topic == "Newton's Laws of Motion"
        assert plan.total_concepts == 3
        assert plan.grade_level == "Grade 11"
        assert plan.concepts[0].title == "Newton's First Law"
        assert plan.concepts[1].title == "Newton's Second Law"
        assert plan.concepts[2].title == "Newton's Third Law"

    def test_deep_nodes_folded(self):
        nodes = [
            _MockGraphNode("r", "Root", "Root summary", level=0, order=0, children_ids=["c1"]),
            _MockGraphNode("c1", "Child", "Child summary", level=1, order=1, parent_id="r"),
            _MockGraphNode("gc1", "Grandchild", "Deep summary", level=2, order=2, parent_id="c1"),
        ]
        graph = _MockConceptGraph("Test", nodes)
        plan = lesson_plan_from_graph(graph)
        # Only level 0 and 1 included.
        assert plan.total_concepts == 2
        titles = [c.title for c in plan.concepts]
        assert "Grandchild" not in titles

    def test_visual_suggestions_populated(self):
        graph = _make_graph()
        plan = lesson_plan_from_graph(graph)
        # All nodes have visual/spatial content → should have suggestions.
        for concept in plan.concepts:
            assert len(concept.visual_suggestions) > 0


# ── Session audit standalone tests ────────────────────────


class TestSessionAudit:
    def test_record_and_count(self):
        audit = SessionAudit()
        audit.record("anticipation", "cache_hit", "concept=1")
        audit.record("anticipation", "cache_hit", "concept=2")
        audit.record("anticipation", "cache_miss", "concept=3")
        assert audit.count("anticipation", "cache_hit") == 2
        assert audit.count("anticipation", "cache_miss") == 1

    def test_events_for_system(self):
        audit = SessionAudit()
        audit.record("anticipation", "cache_hit")
        audit.record("layout", "template_used")
        assert len(audit.events_for("anticipation")) == 1
        assert len(audit.events_for("layout")) == 1

    def test_summary_structure(self):
        audit = SessionAudit()
        audit.record("anticipation", "pre_generated")
        audit.record("anticipation", "cache_hit")
        summary = audit.summary()
        assert "elapsed_seconds" in summary
        assert "total_events" in summary
        assert summary["total_events"] == 2

    def test_summary_text(self):
        audit = SessionAudit()
        audit.record("anticipation", "cache_hit")
        text = audit.summary_text()
        assert "SESSION AUDIT" in text


class TestGetPromptsForConcept:
    """Accessor that exposes pre-generated prompts for the prompt builder."""

    def test_returns_prompts_for_concept(self):
        engine = AnticipationEngine()
        engine._prompts[(2, 0)] = "Draw a lens diagram"
        engine._prompts[(2, 1)] = "Draw a ray diagram"
        engine._prompts[(3, 0)] = "Draw a wave diagram"

        result = engine.get_prompts_for_concept(2)
        assert len(result) == 2
        assert "Draw a lens diagram" in result
        assert "Draw a ray diagram" in result

    def test_returns_empty_when_not_warmed(self):
        engine = AnticipationEngine()
        assert engine.get_prompts_for_concept(0) == []

    def test_returns_empty_for_wrong_concept(self):
        engine = AnticipationEngine()
        engine._prompts[(1, 0)] = "Draw a force diagram"
        assert engine.get_prompts_for_concept(5) == []


class TestLoweredThreshold:
    """Same-concept matching uses lower threshold (0.15 vs 0.3)."""

    def test_same_concept_lower_threshold_hits(self):
        """A moderate-similarity prompt should match at the same concept index."""
        engine = AnticipationEngine()
        engine._cache[(0, 0)] = {"title": "SHM", "elements": []}
        engine._prompts[(0, 0)] = (
            "Draw a detailed diagram for: Simple Harmonic Motion. "
            "Context: A mass-spring system with displacement x from equilibrium."
        )
        # Agent writes a somewhat different prompt for the same concept
        result = engine.match(
            "Draw a mass-spring system showing displacement and restoring force",
            concept_index=0,
        )
        # With lowered threshold (0.15) this should match
        assert result is not None
        assert result["title"] == "SHM"

    def test_adjacent_concept_keeps_higher_threshold(self):
        """Adjacent concept (±1) still needs 0.3 threshold."""
        engine = AnticipationEngine()
        engine._cache[(0, 0)] = {"title": "X", "elements": []}
        engine._prompts[(0, 0)] = "Draw a spring mass system oscillating"
        # Very loose match — should fail at 0.3 threshold for adjacent concept
        result = engine.match(
            "Draw a totally different topic about light refraction",
            concept_index=1,
        )
        assert result is None


class TestConceptIndexDirectMatch:
    """Direct concept-index matching bypasses Jaccard for same-concept hits."""

    def test_direct_hit_ignores_prompt_wording(self):
        """Cache hit purely by concept index, even with zero token overlap."""
        engine = AnticipationEngine()
        spec = {"title": "SHM", "elements": [{"id": "e1"}]}
        engine._cache[(2, 0)] = spec
        engine._prompts[(2, 0)] = "Draw a detailed educational diagram for: SHM"

        # Completely different wording — Jaccard would score ~0
        result = engine.match(
            "A pendulum swinging back and forth between two extremes",
            concept_index=2,
        )
        assert result is not None
        assert result["title"] == "SHM"

    def test_direct_hit_prefers_suggestion_zero(self):
        """When multiple suggestions cached for a concept, returns index 0."""
        engine = AnticipationEngine()
        engine._cache[(1, 0)] = {"title": "First", "elements": []}
        engine._cache[(1, 1)] = {"title": "Second", "elements": []}
        engine._prompts[(1, 0)] = "prompt zero"
        engine._prompts[(1, 1)] = "prompt one"

        result = engine.match("anything", concept_index=1)
        assert result is not None
        assert result["title"] == "First"

    def test_no_direct_hit_for_wrong_concept(self):
        """Concept index mismatch falls through to Jaccard loop."""
        engine = AnticipationEngine()
        engine._cache[(2, 0)] = {"title": "Wrong", "elements": []}
        engine._prompts[(2, 0)] = "completely unrelated words about circuits"

        result = engine.match(
            "even more unrelated words about biology",
            concept_index=5,
        )
        assert result is None  # no direct hit, Jaccard also misses

    def test_direct_hit_audit_event(self):
        """Concept-index hit records audit event."""
        audit = SessionAudit()
        engine = AnticipationEngine(audit=audit)
        engine._cache[(0, 0)] = {"title": "Test", "elements": []}
        engine._prompts[(0, 0)] = "cached prompt"

        engine.match("any prompt", concept_index=0)
        assert audit.count("anticipation", "concept_index_hit") == 1
