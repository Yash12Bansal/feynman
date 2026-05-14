"""Phase 5a-1 — ``drain_perception_feedback`` (the ``llm_node`` injection core).

The override in :class:`FeynmanAgent.llm_node` is a one-liner around
:func:`drain_perception_feedback`. These tests target the helper directly
so we don't need to construct a real ``Agent`` or stub
``Agent.default.llm_node`` (which is a class-level descriptor).
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from feynman.agent.board_verifier import PerceptionFeedback
from feynman.agent.state_machine import TeachingStateMachine
from feynman.agent.teaching_context import TeachingContext
from feynman.livekit.worker import drain_perception_feedback


def _make_tc() -> TeachingContext:
    session_id = uuid4()
    return TeachingContext(
        session_id=session_id,
        state_machine=TeachingStateMachine(session_id=session_id),
    )


def _make_feedback(claim: str = "hypotenuse", suggestion: str = "side_AB") -> PerceptionFeedback:
    return PerceptionFeedback(
        tool_name="highlight_pulse",
        original_claim=claim,
        score=2,
        issue="wrong target",
        suggested_target=suggestion,
        suggested_tag_syntax=f'<highlight target="{suggestion}"/>',
    )


class _FakeChatCtx:
    """Captures :meth:`add_message` calls — same shape as livekit's ChatContext."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def add_message(self, *, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})


def test_empty_queue_is_noop() -> None:
    tc = _make_tc()
    chat_ctx = _FakeChatCtx()
    count = drain_perception_feedback(tc, chat_ctx)  # type: ignore[arg-type]
    assert count == 0
    assert chat_ctx.messages == []


def test_single_feedback_injects_one_user_role_note() -> None:
    tc = _make_tc()
    tc.perception_feedback_queue.append(_make_feedback())
    chat_ctx = _FakeChatCtx()
    count = drain_perception_feedback(tc, chat_ctx)  # type: ignore[arg-type]
    assert count == 1
    assert len(chat_ctx.messages) == 1
    msg = chat_ctx.messages[0]
    assert msg["role"] == "user"
    assert msg["content"].startswith("[PERCEPTION_FEEDBACK]")
    assert "side_AB" in msg["content"]
    assert '<highlight target="side_AB"/>' in msg["content"]


def test_drain_clears_queue() -> None:
    tc = _make_tc()
    tc.perception_feedback_queue.append(_make_feedback())
    tc.perception_feedback_queue.append(_make_feedback(claim="x", suggestion="y"))
    drain_perception_feedback(tc, _FakeChatCtx())  # type: ignore[arg-type]
    assert tc.perception_feedback_queue == []


def test_multiple_feedbacks_injected_in_stream_order() -> None:
    tc = _make_tc()
    tc.perception_feedback_queue.append(_make_feedback(claim="A", suggestion="A_real"))
    tc.perception_feedback_queue.append(_make_feedback(claim="B", suggestion="B_real"))
    tc.perception_feedback_queue.append(_make_feedback(claim="C", suggestion="C_real"))
    chat_ctx = _FakeChatCtx()
    drain_perception_feedback(tc, chat_ctx)  # type: ignore[arg-type]
    assert len(chat_ctx.messages) == 3
    assert "A_real" in chat_ctx.messages[0]["content"]
    assert "B_real" in chat_ctx.messages[1]["content"]
    assert "C_real" in chat_ctx.messages[2]["content"]


def test_each_message_has_perception_feedback_prefix() -> None:
    tc = _make_tc()
    tc.perception_feedback_queue.append(_make_feedback(claim="A", suggestion="A_real"))
    tc.perception_feedback_queue.append(_make_feedback(claim="B", suggestion="B_real"))
    chat_ctx = _FakeChatCtx()
    drain_perception_feedback(tc, chat_ctx)  # type: ignore[arg-type]
    for msg in chat_ctx.messages:
        assert msg["role"] == "user"
        assert msg["content"].startswith("[PERCEPTION_FEEDBACK]")
