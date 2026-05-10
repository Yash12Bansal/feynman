"""State-aware decorator that gates LLM tool calls on the current
`TeachingState`.

Phase 2B applies `@state_constrained(forbidden_states={HANDLING_DOUBT}, ...)`
to a small set of escape-hatch tools — `start_doubt_branch` (no nested doubts
in v0), `advance_concept` (cannot skip ahead mid-doubt), `switch_board` (cannot
sidestep the doubt board). When the LLM tries to call one of these inside a
doubt branch, the decorator raises `ToolConstraintError`. LiveKit's
`function_tool` machinery surfaces the message back to the LLM as a normal
tool error so the agent can correct course.

Usage — `@function_tool()` MUST sit on the outside (LiveKit registers the
constraint-checked async function):

    @function_tool()
    @state_constrained(
        forbidden_states={TeachingState.HANDLING_DOUBT},
        error_template="...",
    )
    async def advance_concept(ctx: RunContext) -> str: ...
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import TypeVar

from feynman.agent.states import TeachingState
from feynman.common.exceptions import ToolConstraintError

T = TypeVar("T")
ToolFn = Callable[..., Awaitable[T]]


def state_constrained(
    *,
    forbidden_states: set[TeachingState] | None = None,
    allowed_states: set[TeachingState] | None = None,
    error_template: str | None = None,
) -> Callable[[ToolFn[T]], ToolFn[T]]:
    """Decorator that raises `ToolConstraintError` if the current
    `TeachingState` is forbidden (or not in `allowed_states`, when set).

    Looks up the state via `ctx.userdata.state_machine.current.state`.
    `ctx` is expected to be the first positional argument (LiveKit's
    `RunContext`).
    """

    def decorator(fn: ToolFn[T]) -> ToolFn[T]:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            if not args:
                raise ToolConstraintError(
                    f"{fn.__name__}: state_constrained requires `ctx` as first arg."
                )
            ctx = args[0]
            current = _current_state(ctx)
            if current is None:
                # No state machine available (e.g. tests without TC). Fall through.
                return await fn(*args, **kwargs)

            if forbidden_states and current in forbidden_states:
                raise ToolConstraintError(
                    error_template or f"{fn.__name__} is disabled in {current.name} state."
                )
            if allowed_states is not None and current not in allowed_states:
                allowed = sorted(s.name for s in allowed_states)
                raise ToolConstraintError(
                    error_template
                    or f"{fn.__name__} is only available in {allowed} (currently {current.name})."
                )

            return await fn(*args, **kwargs)

        return wrapper

    return decorator


def _current_state(ctx: object) -> TeachingState | None:
    """Read `ctx.userdata.state_machine.current.state`, defending against
    mocks / unit-test fixtures that don't fully populate the chain."""
    userdata = getattr(ctx, "userdata", None)
    if userdata is None:
        return None
    state_machine = getattr(userdata, "state_machine", None)
    if state_machine is None:
        return None
    current = getattr(state_machine, "current", None)
    if current is None:
        return None
    state = getattr(current, "state", None)
    if not isinstance(state, TeachingState):
        return None
    return state
