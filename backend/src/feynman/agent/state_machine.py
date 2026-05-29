# TODO(DEADCODE): file unused in active pipelines (precompute-gen / lecture-playback / ask-feynman) — interactive live-teaching subsystem (parked). See docs/engineering/13-redundant-code-audit.md Group 2. Safe to delete.
# """Async teaching state machine with stack-based branching.

# This is the core of Feynman's teaching intelligence. The state machine
# navigates a tree/graph structure where:
# - Main branch = linear sequence of concepts to teach
# - Doubt branches = spawn when a student asks a question, merge back when resolved
# - Nested doubts = branches from branches, same pattern

# The stack-based approach means we always know where we are and where to return.
# """

# from __future__ import annotations

# import asyncio
# from dataclasses import dataclass, field
# from datetime import datetime
# from typing import TYPE_CHECKING, Any
# from uuid import UUID, uuid4

# import structlog

# from feynman.agent.states import TeachingState

# if TYPE_CHECKING:
#     from feynman_teaching_kernel import ChecklistItem

#     from feynman.agent.doubt_orchestrator import ReturnAnchor

# logger = structlog.get_logger()


# @dataclass
# class BranchContext:
#     """Context for a single branch in the teaching tree.

#     The doubt-orchestrator fields (`return_anchor`, `checklist`, `started_at`)
#     are populated only on doubt branches by `DoubtOrchestrator.on_push`. The
#     root branch and any future non-doubt branches leave them as defaults.
#     """

#     id: UUID = field(default_factory=uuid4)
#     state: TeachingState = TeachingState.TEACHING
#     concept: str = ""
#     metadata: dict[str, Any] = field(default_factory=dict)
#     return_anchor: ReturnAnchor | None = None
#     checklist: list[ChecklistItem] = field(default_factory=list)
#     started_at: datetime | None = None


# class TeachingStateMachine:
#     """Async state machine for managing a teaching session.

#     Uses a stack to handle branching (doubts) and merging (returning to main flow).
#     Each branch has its own context, and the stack preserves the return path.
#     """

#     def __init__(self, session_id: UUID) -> None:
#         self.session_id = session_id
#         self._stack: list[BranchContext] = [BranchContext()]
#         self._lock = asyncio.Lock()

#     @property
#     def current(self) -> BranchContext:
#         return self._stack[-1]

#     @property
#     def state(self) -> TeachingState:
#         return self.current.state

#     @property
#     def depth(self) -> int:
#         return len(self._stack)

#     async def transition(self, new_state: TeachingState) -> None:
#         """Transition to a new state within the current branch."""
#         async with self._lock:
#             old_state = self.current.state
#             self.current.state = new_state
#             logger.info(
#                 "state.transition",
#                 session_id=str(self.session_id),
#                 branch_id=str(self.current.id),
#                 old_state=old_state,
#                 new_state=new_state,
#                 depth=self.depth,
#             )

#     async def push_branch(self, concept: str = "", **metadata: Any) -> BranchContext:
#         """Push a new branch onto the stack (e.g., handling a doubt)."""
#         async with self._lock:
#             branch = BranchContext(
#                 state=TeachingState.HANDLING_DOUBT,
#                 concept=concept,
#                 metadata=metadata,
#             )
#             self._stack.append(branch)
#             logger.info(
#                 "branch.pushed",
#                 session_id=str(self.session_id),
#                 branch_id=str(branch.id),
#                 concept=concept,
#                 depth=self.depth,
#             )
#             return branch

#     async def pop_branch(self) -> BranchContext:
#         """Pop the current branch, returning to the parent branch."""
#         async with self._lock:
#             if self.depth <= 1:
#                 raise RuntimeError("Cannot pop the root branch")
#             popped = self._stack.pop()
#             logger.info(
#                 "branch.popped",
#                 session_id=str(self.session_id),
#                 popped_id=str(popped.id),
#                 resumed_id=str(self.current.id),
#                 depth=self.depth,
#             )
#             return popped
