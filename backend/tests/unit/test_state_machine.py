# TODO(DEADCODE): tests parked/dead modules (Group 1/2/3); see docs/engineering/13-redundant-code-audit.md. Safe to delete.
# """Tests for the teaching state machine."""

# from uuid import uuid4

# import pytest

# from feynman.agent.state_machine import TeachingStateMachine
# from feynman.agent.states import TeachingState


# @pytest.fixture
# def sm():
#     return TeachingStateMachine(session_id=uuid4())


# async def test_initial_state(sm: TeachingStateMachine):
#     assert sm.state == TeachingState.TEACHING
#     assert sm.depth == 1


# async def test_transition(sm: TeachingStateMachine):
#     await sm.transition(TeachingState.ASKING_QUESTION)
#     assert sm.state == TeachingState.ASKING_QUESTION


# async def test_push_and_pop_branch(sm: TeachingStateMachine):
#     await sm.transition(TeachingState.TEACHING)

#     branch = await sm.push_branch(concept="Newton's 3rd law")
#     assert sm.depth == 2
#     assert sm.state == TeachingState.HANDLING_DOUBT
#     assert branch.concept == "Newton's 3rd law"

#     popped = await sm.pop_branch()
#     assert sm.depth == 1
#     assert sm.state == TeachingState.TEACHING
#     assert popped.id == branch.id


# async def test_nested_branches(sm: TeachingStateMachine):
#     await sm.push_branch(concept="forces")
#     await sm.push_branch(concept="what is mass?")
#     assert sm.depth == 3

#     await sm.pop_branch()
#     assert sm.depth == 2

#     await sm.pop_branch()
#     assert sm.depth == 1


# async def test_cannot_pop_root(sm: TeachingStateMachine):
#     with pytest.raises(RuntimeError, match="Cannot pop the root branch"):
#         await sm.pop_branch()
