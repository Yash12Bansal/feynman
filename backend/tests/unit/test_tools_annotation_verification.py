"""Phase 5a-1 — ``_schedule_annotation_verification`` (tool-side helper).

These tests cover the scheduler in :mod:`feynman.agent.tools` that all 4
annotation tools call after publishing. They patch
``asyncio.create_task`` so we can assert what would have been scheduled
without actually running a verification.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

from feynman.agent.board_verifier import PerceptionFeedback
from feynman.agent.state_machine import TeachingStateMachine
from feynman.agent.teaching_context import TeachingContext
from feynman.agent.tools import _schedule_annotation_verification


def _make_tc(*, with_verifier: bool = True, with_dict: bool = True) -> TeachingContext:
    session_id = uuid4()
    tc = TeachingContext(
        session_id=session_id,
        state_machine=TeachingStateMachine(session_id=session_id),
    )
    if with_verifier:
        # Minimum surface: schedule reads .request_annotation_verification and
        # passes a coroutine to asyncio.create_task. The fake returns a
        # placeholder coroutine the test never awaits.

        async def _fake_request_annotation_verification(**_kwargs: Any) -> None:
            return None

        tc.board_verifier = SimpleNamespace(
            request_annotation_verification=_fake_request_annotation_verification,
        )
    if with_dict:
        tc.current_diagram_dictionary = {
            "line-1": {"role": "hypotenuse", "semantic": "long side"},
            "line-2": {"role": "adjacent", "semantic": "bottom"},
        }
    return tc


def _ctx(tc: TeachingContext) -> Any:
    return SimpleNamespace(userdata=tc)


def test_schedule_skipped_when_no_verifier_configured() -> None:
    tc = _make_tc(with_verifier=False)
    ctx = _ctx(tc)
    with patch("feynman.agent.tools.asyncio.create_task") as create_task:
        _schedule_annotation_verification(
            ctx,
            tool_name="highlight_pulse",
            original_claim="hypotenuse",
            target_id="line-1",
        )
    create_task.assert_not_called()


def test_schedule_skipped_when_no_diagram_active() -> None:
    tc = _make_tc(with_dict=False)
    ctx = _ctx(tc)
    with patch("feynman.agent.tools.asyncio.create_task") as create_task:
        _schedule_annotation_verification(
            ctx,
            tool_name="highlight_pulse",
            original_claim="hypotenuse",
            target_id="line-1",
        )
    create_task.assert_not_called()


def test_schedule_runs_when_verifier_and_diagram_present() -> None:
    tc = _make_tc()
    ctx = _ctx(tc)
    with patch("feynman.agent.tools.asyncio.create_task") as create_task:
        _schedule_annotation_verification(
            ctx,
            tool_name="highlight_pulse",
            original_claim="hypotenuse",
            target_id="line-1",
        )
    assert create_task.called
    # Dedup key recorded for the same emission.
    assert (
        "highlight_pulse",
        "line-1",
        tc.current_concept_index,
    ) in tc.annotation_verified


def test_dedup_prevents_double_schedule_on_same_target() -> None:
    tc = _make_tc()
    ctx = _ctx(tc)
    with patch("feynman.agent.tools.asyncio.create_task") as create_task:
        _schedule_annotation_verification(
            ctx,
            tool_name="highlight_pulse",
            original_claim="hypotenuse",
            target_id="line-1",
        )
        _schedule_annotation_verification(
            ctx,
            tool_name="highlight_pulse",
            original_claim="hypotenuse",
            target_id="line-1",
        )
    assert create_task.call_count == 1


def test_different_targets_schedule_separately() -> None:
    tc = _make_tc()
    ctx = _ctx(tc)
    with patch("feynman.agent.tools.asyncio.create_task") as create_task:
        _schedule_annotation_verification(
            ctx,
            tool_name="highlight_pulse",
            original_claim="hypotenuse",
            target_id="line-1",
        )
        _schedule_annotation_verification(
            ctx,
            tool_name="highlight_pulse",
            original_claim="adjacent",
            target_id="line-2",
        )
    assert create_task.call_count == 2


def test_different_tools_on_same_target_dedup_separately() -> None:
    tc = _make_tc()
    ctx = _ctx(tc)
    with patch("feynman.agent.tools.asyncio.create_task") as create_task:
        _schedule_annotation_verification(
            ctx,
            tool_name="highlight_pulse",
            original_claim="hypotenuse",
            target_id="line-1",
        )
        _schedule_annotation_verification(
            ctx,
            tool_name="pin_label_near",
            original_claim="hypotenuse",
            target_id="line-1",
        )
    assert create_task.call_count == 2


def test_callback_enqueues_feedback_within_budget() -> None:
    """The on_feedback closure built inside the scheduler enqueues correctly
    and respects the per-concept budget of 2."""
    tc = _make_tc()
    ctx = _ctx(tc)

    captured_callbacks: list[Any] = []

    async def fake_request(**kwargs: Any) -> None:
        captured_callbacks.append(kwargs["on_feedback"])

    tc.board_verifier = SimpleNamespace(request_annotation_verification=fake_request)

    real_create_task = MagicMock()

    def make_callback(target_id: str) -> Any:
        with patch("feynman.agent.tools.asyncio.create_task", real_create_task):
            _schedule_annotation_verification(
                ctx,
                tool_name="highlight_pulse",
                original_claim="hypotenuse",
                target_id=target_id,
            )
        # Pull the coroutine that would have been scheduled and step it
        # synchronously enough to capture the callback.
        coro = real_create_task.call_args[0][0]
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(coro)
        finally:
            loop.close()
        return captured_callbacks[-1]

    cb_1 = make_callback("line-1")
    cb_2 = make_callback("line-2")
    cb_3 = make_callback("line-3")

    fb = PerceptionFeedback(
        tool_name="highlight_pulse",
        original_claim="hypotenuse",
        score=2,
        issue="wrong",
        suggested_target="x",
        suggested_tag_syntax='<highlight target="x"/>',
    )
    cb_1(fb, None)
    cb_2(fb, None)
    cb_3(fb, None)  # Should be dropped — budget exceeded.

    assert len(tc.perception_feedback_queue) == 2
    assert tc.perception_feedback_budget_used[tc.current_concept_index] == 2


def test_callback_drops_stale_feedback_after_concept_advance() -> None:
    tc = _make_tc()
    ctx = _ctx(tc)

    captured_callbacks: list[Any] = []

    async def fake_request(**kwargs: Any) -> None:
        captured_callbacks.append(kwargs["on_feedback"])

    tc.board_verifier = SimpleNamespace(request_annotation_verification=fake_request)
    real_create_task = MagicMock()

    with patch("feynman.agent.tools.asyncio.create_task", real_create_task):
        _schedule_annotation_verification(
            ctx,
            tool_name="highlight_pulse",
            original_claim="hypotenuse",
            target_id="line-1",
        )
    coro = real_create_task.call_args[0][0]
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(coro)
    finally:
        loop.close()
    cb = captured_callbacks[-1]

    # Simulate concept advance.
    tc.current_concept_index = 1

    fb = PerceptionFeedback(
        tool_name="highlight_pulse",
        original_claim="hypotenuse",
        score=2,
        issue="wrong",
        suggested_target="x",
        suggested_tag_syntax='<highlight target="x"/>',
    )
    cb(fb, None)

    assert tc.perception_feedback_queue == []
