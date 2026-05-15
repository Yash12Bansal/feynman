"""Phase 5a-3 — original-claim retention in draw_design_diagram.

The drift check's cumulative-integrity branch compares the diagram's CURRENT
rendering against its ORIGINAL claim across modifications. That requires the
first ``draw_design_diagram(prompt=...)`` call to retain ``prompt`` keyed by
``element_id`` regardless of how many ``modify_design_diagram`` calls follow.

Tests cover:

* draw writes the original claim to ``tc.original_diagram_claims``
* second draw with the same element_id does NOT overwrite (defensive — the
  ID generator should not collide, but if it ever does we preserve intent)
* modify_design_diagram leaves ``original_diagram_claims`` untouched
* ``reset_for_new_topic`` clears the dict + the related drift fields
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from feynman.agent.board import BoardManager
from feynman.agent.session_audit import SessionAudit
from feynman.agent.state_machine import TeachingStateMachine
from feynman.agent.teaching_context import TeachingContext
from feynman.visuals.schemas import DrawDesignDiagramInstruction

SAMPLE_SPEC: dict = {
    "title": "Free Body Diagram",
    "description": "Forces on a 5kg block",
    "width": 900,
    "height": 650,
    "elements": [],
}

MODIFIED_SPEC: dict = {
    "title": "Free Body Diagram",
    "description": "Forces on a 5kg block + friction",
    "width": 900,
    "height": 650,
    "elements": [],
}


def _make_mock_ctx_for_draw(
    *,
    cache_hit_spec: dict | None = None,
    original_claims: dict[str, str] | None = None,
) -> MagicMock:
    """Build a RunContext mock for a draw_design_diagram invocation.

    Mirrors ``test_tools_slide_pending`` but adds the ``original_diagram_claims``
    + ``diagram_version`` fields the retention code reads/writes.
    """
    ctx = MagicMock()
    ctx.wait_for_playout = AsyncMock()
    ctx.session.room_io.room.local_participant.publish_data = AsyncMock()
    ctx.session.current_agent.update_instructions = AsyncMock()

    userdata = MagicMock()
    userdata.board_manager = BoardManager()
    userdata.audit = SessionAudit()
    userdata.current_concept_index = 0
    userdata.current_concept = None
    userdata.lesson_plan = None
    userdata.anticipation = MagicMock()
    userdata.anticipation.match = MagicMock(return_value=cache_hit_spec)
    # Phase 5a-3 fields the retention code touches.
    userdata.original_diagram_claims = original_claims if original_claims is not None else {}
    userdata.diagram_version = {}
    userdata.diagram_intent_verified = set()
    userdata.diagram_layout_verified = set()
    userdata.last_diagram_claims = {}
    userdata.current_diagram_dictionary = {}
    # Phase 5a-2: short-circuit the diagram-verification scheduler.
    userdata.board_verifier = None
    ctx.userdata = userdata
    return ctx


# ── draw_design_diagram writes ───────────────────────────


@pytest.mark.asyncio
async def test_draw_writes_original_claim_on_cache_hit() -> None:
    from feynman.agent.tools import draw_design_diagram

    ctx = _make_mock_ctx_for_draw(cache_hit_spec=SAMPLE_SPEC)
    tc = ctx.userdata

    await draw_design_diagram(ctx, prompt="free body diagram of a 5kg block")

    # The first allocated id from BoardManager is "design-1".
    assert tc.original_diagram_claims == {"design-1": "free body diagram of a 5kg block"}


@pytest.mark.asyncio
async def test_draw_writes_original_claim_on_cache_miss() -> None:
    from feynman.agent.tools import draw_design_diagram

    ctx = _make_mock_ctx_for_draw(cache_hit_spec=None)
    tc = ctx.userdata

    with patch(
        "feynman.agent.design_bridge.generate_design_diagram",
        new_callable=AsyncMock,
        return_value=SAMPLE_SPEC,
    ):
        await draw_design_diagram(ctx, prompt="ladder against a wall")

    assert tc.original_diagram_claims == {"design-1": "ladder against a wall"}


@pytest.mark.asyncio
async def test_draw_does_not_overwrite_existing_original_claim() -> None:
    """Defensive: a duplicate element_id (rare) must not erase prior intent."""
    from feynman.agent.tools import draw_design_diagram

    ctx = _make_mock_ctx_for_draw(
        cache_hit_spec=SAMPLE_SPEC,
        original_claims={"design-1": "original claim from earlier draw"},
    )
    tc = ctx.userdata

    # Force the BoardManager into a state where the next id will be design-1
    # by directly manipulating its counter — easier than driving a full
    # reset cycle.
    tc.board_manager._id_counters["design"] = 0  # next next_id("design") → "design-1"

    await draw_design_diagram(ctx, prompt="should not overwrite")

    assert tc.original_diagram_claims["design-1"] == "original claim from earlier draw"


# ── modify_design_diagram leaves claims alone ────────────


@pytest.mark.asyncio
async def test_modify_does_not_touch_original_diagram_claims() -> None:
    """modify_design_diagram is for in-place updates — original intent stays."""
    from feynman.agent.tools import modify_design_diagram

    ctx = _make_mock_ctx_for_draw()
    tc = ctx.userdata
    bm = tc.board_manager

    # Pre-seed the original claim that draw would have recorded.
    tc.original_diagram_claims = {"design-1": "original FBD prompt"}

    # Pre-store the design spec so modify_design_diagram can find it.
    instr = DrawDesignDiagramInstruction(title="FBD", spec=SAMPLE_SPEC, element_id="design-1")
    bm.record(instr)
    bm.store_design_spec("design-1", SAMPLE_SPEC)

    with patch(
        "feynman.agent.design_bridge.modify_design_diagram_spec",
        new_callable=AsyncMock,
        return_value=MODIFIED_SPEC,
    ):
        await modify_design_diagram(ctx, target_id="design-1", modification="Add friction vector")

    # Original claim untouched, even though the spec was modified.
    assert tc.original_diagram_claims == {"design-1": "original FBD prompt"}


# ── reset_for_new_topic clears drift state ───────────────


def test_reset_for_new_topic_clears_drift_fields() -> None:
    session_id = uuid4()
    tc = TeachingContext(
        session_id=session_id,
        state_machine=TeachingStateMachine(session_id=session_id),
    )
    tc.original_diagram_claims["design-1"] = "alpha"
    tc.original_diagram_claims["design-2"] = "beta"
    tc.last_drift_check_hash = "some-hash"
    tc.drift_feedback_budget_used[0] = 1
    tc.drift_feedback_budget_used[3] = 1

    tc.reset_for_new_topic()

    assert tc.original_diagram_claims == {}
    assert tc.last_drift_check_hash is None
    assert tc.drift_feedback_budget_used == {}


# ── End-to-end: published payload sanity ─────────────────


@pytest.mark.asyncio
async def test_draw_published_payload_still_works(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Smoke: the retention hook doesn't break the publish path."""
    from feynman.agent.tools import draw_design_diagram

    ctx = _make_mock_ctx_for_draw(cache_hit_spec=SAMPLE_SPEC)

    await draw_design_diagram(ctx, prompt="basic diagram")

    publish = ctx.session.room_io.room.local_participant.publish_data
    types = []
    for call in publish.call_args_list:
        raw = call.args[0] if call.args else call.kwargs.get("data")
        types.append(json.loads(raw)["type"])
    assert "draw_design_diagram" in types
