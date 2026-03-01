"""Teaching context — stored in AgentSession.userdata for tool access."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from feynman.agent.board_state import BoardState
from feynman.agent.lesson_plan import ConceptNode, LessonPlan
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
    board_state: BoardState = field(default_factory=BoardState)

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
