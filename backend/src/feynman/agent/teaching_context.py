"""Teaching context — stored in AgentSession.userdata for tool access."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from feynman.agent.anticipation import AnticipationEngine
from feynman.agent.board import BoardManager
from feynman.agent.concept_planner import ConceptTeachingPlan
from feynman.agent.doubt_orchestrator import DoubtOrchestrator
from feynman.agent.lesson_plan import ConceptNode, LessonPlan
from feynman.agent.session_audit import SessionAudit
from feynman.agent.state_machine import TeachingStateMachine


@dataclass
class TeachingContext:
    """Mutable teaching state accessible by all tools via RunContext.userdata.

    Tracks lesson plan progress and wraps the state machine for
    coordinated state management.
    """

    session_id: UUID
    state_machine: TeachingStateMachine
    lesson_plan: LessonPlan | None = None
    current_concept_index: int = 0
    completed_indices: list[int] = field(default_factory=list)
    board_manager: BoardManager = field(default_factory=BoardManager)
    audit: SessionAudit = field(default_factory=SessionAudit)
    anticipation: AnticipationEngine = field(init=False)
    doubt_orchestrator: DoubtOrchestrator = field(init=False)
    curriculum: Any | None = None  # CurriculumData from curriculum_loader (Neo4j)
    board_verifier: Any | None = None  # BoardVerifier (set by worker.py at session start)
    _verified_this_concept: bool = field(default=False, init=False, repr=False)
    # Planning agent: pre-computed teaching plans per concept index.
    concept_plans: dict[int, ConceptTeachingPlan] = field(default_factory=dict)
    doubt_plan: ConceptTeachingPlan | None = None
    # Diagram awareness: dictionary of the diagram currently on the slide,
    # populated from the ``DiagramSpec.dictionary`` field at draw-time and
    # cleared on ``pop_board``. Empty dict means no diagram is active.
    current_diagram_dictionary: dict[str, Any] = field(default_factory=dict)
    # Live overlay tracking — populated as the 4 annotation tools fire on the
    # active slide; consumed by the doubt orchestrator at push time so the
    # snapshot can replay them on resume. Cleared on board swap.
    active_highlights: list[str] = field(default_factory=list)
    active_annotations: list[str] = field(default_factory=list)
    # Reserved for prompt-side context restoration on auto-resume. The doubt
    # orchestrator snapshots this; populating deterministically lands in 2B.
    last_beat_index: int = 0
    # --- COMMENTED OUT: Old ConceptGraph field. Replaced by curriculum. ---
    # concept_graph: Any | None = None  # ConceptGraph from data_pre_compute (optional)
    # _graph_node_map: dict[int, str] | None = field(default=None, init=False, repr=False)
    # --- END COMMENTED OUT ---

    def __post_init__(self) -> None:
        self.anticipation = AnticipationEngine(audit=self.audit)
        self.doubt_orchestrator = DoubtOrchestrator(self)

    @property
    def current_plan(self) -> ConceptTeachingPlan | None:
        """Teaching plan for the current concept (or the active doubt)."""
        if self.state_machine.depth > 1:
            return self.doubt_plan
        return self.concept_plans.get(self.current_concept_index)

    @property
    def current_concept(self) -> ConceptNode | None:
        if self.lesson_plan is None:
            return None
        return self.lesson_plan.concept_at(self.current_concept_index)

    @property
    def is_lesson_complete(self) -> bool:
        if self.lesson_plan is None:
            return False
        return len(self.completed_indices) >= self.lesson_plan.total_concepts

    @property
    def progress_summary(self) -> str:
        if self.lesson_plan is None:
            return "Free-form teaching (no lesson plan)"

        done = len(self.completed_indices)
        total = self.lesson_plan.total_concepts
        current = self.current_concept

        parts = [f"{done}/{total} concepts"]
        if current:
            parts.append(f"Current: {current.title}")
        depth = self.state_machine.depth
        if depth > 1:
            parts.append(f"Branch depth: {depth}")

        return " | ".join(parts)

    def advance(self) -> ConceptNode | None:
        """Mark current concept as completed and move to next.

        Returns the next concept, or None if lesson is complete.
        """
        if self.lesson_plan is None:
            return None

        if self.current_concept_index not in self.completed_indices:
            self.completed_indices.append(self.current_concept_index)

        next_index = self.current_concept_index + 1
        if next_index < self.lesson_plan.total_concepts:
            self.current_concept_index = next_index
            return self.lesson_plan.concept_at(next_index)

        return None

    def reset_for_new_topic(self) -> None:
        """Reset lesson state for a new topic. Called by set_lesson_topic."""
        self.lesson_plan = None
        self.current_concept_index = 0
        self.completed_indices = []
        self.curriculum = None
        self.concept_plans = {}
        self.doubt_plan = None

    @property
    def current_curriculum_concept(self) -> Any | None:
        """Get the CurriculumConcept for the current lesson plan concept.

        Uses direct index lookup — curriculum concepts are already in teaching order.
        No fuzzy matching needed since the LessonPlan was derived from curriculum.
        """
        if not self.curriculum or not self.current_concept:
            return None

        teaching_order = self.curriculum.get_teaching_order()
        concept_level = [c for c in teaching_order if c.level == 0]

        if 0 <= self.current_concept_index < len(concept_level):
            return concept_level[self.current_concept_index]
        return None

    # --- COMMENTED OUT: Old fuzzy ConceptGraph matching. Replaced by direct index. ---
    # @property
    # def current_graph_node(self) -> Any | None:
    #     """Find the ConceptGraph node matching the current concept (fuzzy match)."""
    #     if not self.concept_graph or not self.current_concept:
    #         return None
    #     if self._graph_node_map is None:
    #         self._build_graph_node_map()
    #     node_id = self._graph_node_map.get(self.current_concept_index)
    #     if node_id is None:
    #         return None
    #     try:
    #         return self.concept_graph.nodes.get(node_id)
    #     except (AttributeError, TypeError):
    #         return None
    #
    # def _build_graph_node_map(self) -> None:
    #     """Build concept_index → graph_node_id mapping via fuzzy topic match."""
    #     from feynman.agent.anticipation import _jaccard, _meaningful_tokens
    #     self._graph_node_map = {}
    #     if not self.concept_graph or not self.lesson_plan:
    #         return
    #     try:
    #         graph_nodes = list(self.concept_graph.nodes.values())
    #     except (AttributeError, TypeError):
    #         return
    #     for i in range(self.lesson_plan.total_concepts):
    #         concept = self.lesson_plan.concept_at(i)
    #         if not concept:
    #             continue
    #         plan_tokens = _meaningful_tokens(concept.title)
    #         best_node = None
    #         best_score = 0.0
    #         for node in graph_nodes:
    #             try:
    #                 score = _jaccard(plan_tokens, _meaningful_tokens(node.topic_name))
    #             except (AttributeError, TypeError):
    #                 continue
    #             if score > best_score:
    #                 best_score = score
    #                 best_node = node
    #         if best_node and best_score > 0.2:
    #             self._graph_node_map[i] = best_node.node_id
    # --- END COMMENTED OUT ---
