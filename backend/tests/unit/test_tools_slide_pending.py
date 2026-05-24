"""Tests for the slide_pending emission in the cache-miss branch of
draw_design_diagram (Phase 4 of the split-board work).

The contract:
- Cache MISS → emit exactly one `slide_pending` BEFORE the
  `draw_design_diagram` instruction; both go through `_publish_visual`.
- Cache HIT → no `slide_pending` (loader would just flash and disappear).
- Title falls back to a prompt snippet when no concept metadata is available.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from feynman.agent.board import BoardManager
from feynman.agent.session_audit import SessionAudit

SAMPLE_SPEC: dict = {
    "title": "Free Body Diagram",
    "description": "Forces on a 5kg block",
    "width": 900,
    "height": 650,
    "elements": [],
}


def _make_mock_ctx(
    *,
    cache_hit: bool,
    concept_title: str | None = None,
) -> MagicMock:
    """Build a RunContext mock for a draw_design_diagram invocation."""
    ctx = MagicMock()
    ctx.wait_for_playout = AsyncMock()
    ctx.session.room_io.room.local_participant.publish_data = AsyncMock()
    ctx.session.current_agent.update_instructions = AsyncMock()

    userdata = MagicMock()
    userdata.board_manager = BoardManager()
    userdata.audit = SessionAudit()
    userdata.current_concept_index = 0
    userdata.lesson_plan = None
    userdata.anticipation = MagicMock()
    userdata.anticipation.match = MagicMock(return_value=SAMPLE_SPEC if cache_hit else None)
    if concept_title is not None:
        concept = MagicMock()
        concept.title = concept_title
        userdata.current_concept = concept
    else:
        userdata.current_concept = None
    # Phase 5a-2: short-circuit the diagram-verification scheduler — these
    # tests don't exercise the perception loop.
    userdata.board_verifier = None
    ctx.userdata = userdata
    return ctx


def _published_types(ctx: MagicMock) -> list[str]:
    """Return the list of `type` literals from every publish_data call."""
    publish = ctx.session.room_io.room.local_participant.publish_data
    types: list[str] = []
    for call in publish.call_args_list:
        raw = call.args[0] if call.args else call.kwargs.get("data")
        types.append(json.loads(raw)["type"])
    return types


def _published_payload(ctx: MagicMock, instr_type: str) -> dict:
    """Return the first published payload matching `instr_type`."""
    publish = ctx.session.room_io.room.local_participant.publish_data
    for call in publish.call_args_list:
        raw = call.args[0] if call.args else call.kwargs.get("data")
        decoded = json.loads(raw)
        if decoded.get("type") == instr_type:
            return decoded
    raise AssertionError(f"no published instruction of type {instr_type!r}")


# ── Cache-miss emits slide_pending before the diagram ────────


@pytest.mark.asyncio
async def test_cache_miss_emits_slide_pending_before_diagram() -> None:
    from feynman.agent.tools import draw_design_diagram

    ctx = _make_mock_ctx(cache_hit=False, concept_title="Newton's Second Law")

    with patch(
        "feynman.agent.design_bridge.generate_design_diagram",
        new_callable=AsyncMock,
        return_value=SAMPLE_SPEC,
    ):
        await draw_design_diagram(ctx, prompt="Draw a free body diagram of a 5kg block")

    types = _published_types(ctx)
    # slide_pending must come before draw_design_diagram.
    assert "slide_pending" in types, f"expected slide_pending in {types}"
    assert "draw_design_diagram" in types, f"expected draw_design_diagram in {types}"
    assert types.index("slide_pending") < types.index("draw_design_diagram")

    # And the title carries the concept title.
    payload = _published_payload(ctx, "slide_pending")
    assert payload["title"] == "Newton's Second Law"
    assert payload["panel"] == "slide"


# ── Cache-hit publishes no slide_pending ─────────────────────


@pytest.mark.asyncio
async def test_cache_hit_does_not_emit_slide_pending() -> None:
    from feynman.agent.tools import draw_design_diagram

    ctx = _make_mock_ctx(cache_hit=True, concept_title="Cached Concept")

    # No need to patch generate_design_diagram — the cache short-circuits.
    await draw_design_diagram(ctx, prompt="Draw something already cached")

    types = _published_types(ctx)
    assert "slide_pending" not in types, f"unexpected slide_pending in {types}"
    assert "draw_design_diagram" in types


# ── Missing concept metadata falls back to prompt snippet ────


@pytest.mark.asyncio
async def test_cache_miss_falls_back_to_prompt_when_no_concept() -> None:
    from feynman.agent.tools import draw_design_diagram

    ctx = _make_mock_ctx(cache_hit=False, concept_title=None)
    long_prompt = "Draw a detailed circuit diagram with three resistors in parallel"

    with patch(
        "feynman.agent.design_bridge.generate_design_diagram",
        new_callable=AsyncMock,
        return_value=SAMPLE_SPEC,
    ):
        await draw_design_diagram(ctx, prompt=long_prompt)

    payload = _published_payload(ctx, "slide_pending")
    # Falls back to first 80 chars of the prompt (no crash on missing concept).
    assert payload["title"]
    assert payload["title"] in long_prompt
