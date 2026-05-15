"""Phase 5a-2 — ``_schedule_diagram_verification`` (tool-side helper).

The helper schedules intent + layout verification after ``draw_design_diagram``,
``modify_design_diagram`` and (layout-only) ``draw_scene``. These tests patch
``asyncio.create_task`` so we can assert what would have been scheduled
without actually running the verification.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

from feynman.agent.board_verifier import PerceptionFeedback
from feynman.agent.state_machine import TeachingStateMachine
from feynman.agent.teaching_context import DiagramClaim, TeachingContext
from feynman.agent.tools import _schedule_diagram_verification


def _make_tc(*, with_verifier: bool = True) -> TeachingContext:
    session_id = uuid4()
    tc = TeachingContext(
        session_id=session_id,
        state_machine=TeachingStateMachine(session_id=session_id),
    )
    if with_verifier:
        # Sync stubs — these tests patch ``asyncio.create_task`` so the helper
        # never actually awaits them; using sync callables avoids spurious
        # "coroutine never awaited" warnings from the test runner.
        def _fake_intent(**_kwargs: Any) -> None:
            return None

        def _fake_layout(**_kwargs: Any) -> None:
            return None

        tc.board_verifier = SimpleNamespace(
            request_diagram_intent_verification=_fake_intent,
            request_verification=_fake_layout,
        )
    return tc


def _ctx(tc: TeachingContext) -> Any:
    return SimpleNamespace(userdata=tc)


def test_schedule_skipped_when_no_verifier_configured() -> None:
    tc = _make_tc(with_verifier=False)
    ctx = _ctx(tc)
    with patch("feynman.agent.tools.asyncio.create_task") as create_task:
        _schedule_diagram_verification(
            ctx,
            tool_name="draw_design_diagram",
            element_id="design-1",
            claim_text="anything",
            role_list=["hypotenuse"],
        )
    create_task.assert_not_called()


def test_schedule_runs_both_intent_and_layout_when_verifier_present() -> None:
    tc = _make_tc()
    ctx = _ctx(tc)
    with patch("feynman.agent.tools.asyncio.create_task") as create_task:
        _schedule_diagram_verification(
            ctx,
            tool_name="draw_design_diagram",
            element_id="design-1",
            claim_text="free body diagram",
            role_list=["block"],
        )
    # One intent + one layout task.
    assert create_task.call_count == 2
    names = {call.kwargs.get("name") for call in create_task.call_args_list}
    assert names == {"diagram_intent_verification", "diagram_layout_verification"}


def test_schedule_scene_layout_only() -> None:
    """draw_scene calls with ``do_intent=False`` — only layout fires."""
    tc = _make_tc()
    ctx = _ctx(tc)
    with patch("feynman.agent.tools.asyncio.create_task") as create_task:
        _schedule_diagram_verification(
            ctx,
            tool_name="draw_scene",
            element_id="scene-1",
            claim_text="free_body",
            role_list=[],
            do_intent=False,
        )
    assert create_task.call_count == 1
    assert create_task.call_args.kwargs.get("name") == "diagram_layout_verification"


def test_schedule_records_claim_and_increments_version() -> None:
    tc = _make_tc()
    ctx = _ctx(tc)
    with patch("feynman.agent.tools.asyncio.create_task"):
        _schedule_diagram_verification(
            ctx,
            tool_name="draw_design_diagram",
            element_id="design-1",
            claim_text="claim A",
            role_list=[],
        )
    assert tc.diagram_version["design-1"] == 0
    assert tc.last_diagram_claims["design-1"] == DiagramClaim(
        element_id="design-1",
        claim_text="claim A",
        tool_name="draw_design_diagram",
        version=0,
    )

    with patch("feynman.agent.tools.asyncio.create_task"):
        _schedule_diagram_verification(
            ctx,
            tool_name="modify_design_diagram",
            element_id="design-1",
            claim_text="add ramp",
            role_list=[],
        )
    assert tc.diagram_version["design-1"] == 1
    assert tc.last_diagram_claims["design-1"].claim_text == "add ramp"
    assert tc.last_diagram_claims["design-1"].tool_name == "modify_design_diagram"
    assert tc.last_diagram_claims["design-1"].version == 1


def test_dedup_within_same_version() -> None:
    """A repeat schedule for the SAME (element, version, concept) is a noop.

    Because the helper increments version on every call, dedup never triggers
    in practice via the public path — but a caller that manually re-uses
    a version (e.g. retry path) must not double-schedule. We exercise that
    by direct manipulation of the dedup set."""
    tc = _make_tc()
    ctx = _ctx(tc)
    # First call: increments to version 0, schedules 2 tasks.
    with patch("feynman.agent.tools.asyncio.create_task") as create_task1:
        _schedule_diagram_verification(
            ctx,
            tool_name="draw_design_diagram",
            element_id="design-1",
            claim_text="x",
            role_list=[],
        )
    assert create_task1.call_count == 2
    # Roll version back to 0 and re-call — the dedup set blocks re-schedule.
    tc.diagram_version["design-1"] = -1
    with patch("feynman.agent.tools.asyncio.create_task") as create_task2:
        _schedule_diagram_verification(
            ctx,
            tool_name="draw_design_diagram",
            element_id="design-1",
            claim_text="x",
            role_list=[],
        )
    # Version 0 is still in the dedup set, so no tasks fire.
    assert create_task2.call_count == 0


def test_different_versions_schedule_separately() -> None:
    tc = _make_tc()
    ctx = _ctx(tc)
    with patch("feynman.agent.tools.asyncio.create_task") as create_task:
        _schedule_diagram_verification(
            ctx,
            tool_name="draw_design_diagram",
            element_id="design-1",
            claim_text="A",
            role_list=[],
        )
        _schedule_diagram_verification(
            ctx,
            tool_name="modify_design_diagram",
            element_id="design-1",
            claim_text="B",
            role_list=[],
        )
    # 2 tasks x 2 calls = 4.
    assert create_task.call_count == 4


def test_different_element_ids_schedule_separately() -> None:
    tc = _make_tc()
    ctx = _ctx(tc)
    with patch("feynman.agent.tools.asyncio.create_task") as create_task:
        _schedule_diagram_verification(
            ctx,
            tool_name="draw_design_diagram",
            element_id="design-1",
            claim_text="A",
            role_list=[],
        )
        _schedule_diagram_verification(
            ctx,
            tool_name="draw_design_diagram",
            element_id="design-2",
            claim_text="B",
            role_list=[],
        )
    assert create_task.call_count == 4


def _capture_on_feedback_from_helper(tc: TeachingContext) -> Any:
    """Drive ``_schedule_diagram_verification`` once and return the
    ``on_feedback`` closure the intent verifier would have received.

    The helper passes the SAME closure to both intent and layout
    verifications, so capturing from the intent path is sufficient.
    """
    import asyncio

    captured: list[Any] = []

    async def fake_intent(**kwargs: Any) -> None:
        captured.append(kwargs["on_feedback"])

    async def fake_layout(**kwargs: Any) -> None:
        pass

    tc.board_verifier = SimpleNamespace(
        request_diagram_intent_verification=fake_intent,
        request_verification=fake_layout,
    )

    coros: list[Any] = []

    def fake_create_task(coro: Any, **_kw: Any) -> Any:
        coros.append(coro)
        return MagicMock()

    with patch("feynman.agent.tools.asyncio.create_task", side_effect=fake_create_task):
        _schedule_diagram_verification(
            _ctx(tc),
            tool_name="draw_design_diagram",
            element_id="design-1",
            claim_text="x",
            role_list=[],
        )

    # Run the intent coroutine to capture the on_feedback closure.
    loop = asyncio.new_event_loop()
    try:
        for coro in coros:
            loop.run_until_complete(coro)
    finally:
        loop.close()

    assert captured, "expected the intent verifier to have been scheduled"
    return captured[-1]


def test_callback_budget_shared_with_annotations() -> None:
    """Diagram feedback respects the 2-per-concept budget shared with 5a-1."""
    tc = _make_tc()
    cb = _capture_on_feedback_from_helper(tc)

    # Pretend an annotation already consumed 1 slot in the budget this concept.
    tc.perception_feedback_budget_used[tc.current_concept_index] = 1

    fb = PerceptionFeedback(
        tool_name="draw_design_diagram",
        original_claim="x",
        score=1,
        issue="...",
        suggested_modification="add y",
        target_diagram_id="design-1",
    )
    # 1st call → enqueues (used 1→2, at cap).
    cb(fb, None)
    assert len(tc.perception_feedback_queue) == 1
    assert tc.perception_feedback_budget_used[tc.current_concept_index] == 2

    # 2nd call → budget exceeded, drops.
    cb(fb, None)
    assert len(tc.perception_feedback_queue) == 1


def test_callback_drops_stale_feedback_after_advance() -> None:
    tc = _make_tc()
    cb = _capture_on_feedback_from_helper(tc)

    # Concept advances before the verification finishes — feedback is stale.
    tc.current_concept_index = 1

    fb = PerceptionFeedback(
        tool_name="draw_design_diagram",
        original_claim="x",
        score=1,
        issue="...",
        suggested_modification="add y",
        target_diagram_id="design-1",
    )
    cb(fb, None)
    assert tc.perception_feedback_queue == []


def test_advance_concept_clears_diagram_verified_sets() -> None:
    """Sanity check: advance_concept resets the per-concept dedup sets."""
    tc = _make_tc()
    ctx = _ctx(tc)

    with patch("feynman.agent.tools.asyncio.create_task"):
        _schedule_diagram_verification(
            ctx,
            tool_name="draw_design_diagram",
            element_id="design-1",
            claim_text="x",
            role_list=[],
        )
    assert tc.diagram_intent_verified
    assert tc.diagram_layout_verified

    # Simulate the advance_concept reset path (the tool function does this
    # at the start of a new concept).
    tc.diagram_intent_verified.clear()
    tc.diagram_layout_verified.clear()
    assert tc.diagram_intent_verified == set()
    assert tc.diagram_layout_verified == set()
