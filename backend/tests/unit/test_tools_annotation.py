"""Tests for the four slide-annotation tools (diagram awareness)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from feynman.agent.board import BoardManager
from feynman.agent.tools import (
    bracket,
    draw_callout,
    highlight_pulse,
    pin_label_near,
)


def _make_mock_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.wait_for_playout = AsyncMock()
    ctx.session.room_io.room.local_participant.publish_data = AsyncMock()
    userdata = MagicMock()
    userdata.board_manager = BoardManager()
    userdata.current_concept = None
    userdata.lesson_plan = None
    userdata.current_concept_index = 0
    # Phase 5a-1: short-circuit verification scheduling — these tests don't
    # exercise the vision loop.
    userdata.board_verifier = None
    # Diagram dictionary for the ladder problem (role → element_id resolver).
    # `bounds` is required for frontend positioning; the annotation tools
    # reject entries without bounds so a bogus instruction never reaches the
    # silent-drop path in SlideAnnotationLayer.
    userdata.current_diagram_dictionary = {
        "side_AB": {
            "role": "hypotenuse",
            "semantic": "the ladder, 10 m",
            "bounds": [120, 100, 280, 360],
        },
        "side_BC": {
            "role": "opposite",
            "semantic": "the wall",
            "bounds": [380, 80, 4, 400],
        },
        "side_AC": {
            "role": "adjacent",
            "semantic": "the ground",
            "bounds": [120, 470, 280, 4],
        },
    }
    ctx.userdata = userdata
    return ctx


def _published_payload(ctx: MagicMock) -> dict:
    call_args = ctx.session.room_io.room.local_participant.publish_data.call_args
    return json.loads(call_args[0][0])


@pytest.mark.asyncio
async def test_pin_label_near_resolves_role() -> None:
    ctx = _make_mock_ctx()
    result = await pin_label_near(
        ctx,
        element_or_role="hypotenuse",
        text="10 m",
        position="above",
    )
    assert "side_AB" in result
    payload = _published_payload(ctx)
    assert payload["type"] == "pin_label"
    assert payload["panel"] == "slide"
    assert payload["target_element_id"] == "side_AB"
    assert payload["text"] == "10 m"
    assert payload["position"] == "above"
    # Phase 2: annotations default to sentence-boundary sync so the label
    # lands as the agent finishes the relevant clause, not ~800ms before.
    assert payload["sync_mode"] == "after_next_sentence"


@pytest.mark.asyncio
async def test_all_annotation_tools_default_to_sentence_boundary_sync() -> None:
    """Phase 2 sync default — every annotation tool emits ``after_next_sentence``."""
    for tool, kwargs in [
        (pin_label_near, {"element_or_role": "hypotenuse", "text": "10 m"}),
        (draw_callout, {"from_element": "hypotenuse", "text": "the ladder"}),
        (bracket, {"element_a": "hypotenuse", "element_b": "adjacent", "label": "Δ"}),
        (highlight_pulse, {"element_or_role": "hypotenuse"}),
    ]:
        ctx = _make_mock_ctx()
        await tool(ctx, **kwargs)  # type: ignore[arg-type]
        payload = _published_payload(ctx)
        assert payload["sync_mode"] == "after_next_sentence", (
            f"{tool.__name__} must default to sentence-boundary sync (Phase 2)"
        )


@pytest.mark.asyncio
async def test_pin_label_near_unknown_role_publishes_soft_target() -> None:
    """Phase 1: unknown role no longer blocks publish. The tool emits a
    ``target.kind == "role"`` instruction so the frontend can try a live-DOM
    resolution; backend logs a warning but doesn't fail the LLM call."""
    ctx = _make_mock_ctx()
    result = await pin_label_near(ctx, element_or_role="the line in red", text="60°")
    # Tool result reads as a success — the dictionary miss is a soft warning,
    # not an error the LLM needs to retry on.
    assert "the line in red" in result
    payload = _published_payload(ctx)
    assert payload["type"] == "pin_label"
    # Legacy field carries the raw handle (back-compat with frontend that
    # only reads `target_element_id`); the structured `target` carries kind.
    assert payload["target_element_id"] == "the line in red"
    assert payload["target"]["kind"] == "role"
    assert payload["target"]["value"] == "the line in red"


@pytest.mark.asyncio
async def test_highlight_pulse_errors_with_no_diagram() -> None:
    """Empty dictionary (no diagram drawn yet) → empty-state error string."""
    ctx = _make_mock_ctx()
    ctx.userdata.current_diagram_dictionary = {}
    result = await highlight_pulse(ctx, element_or_role="hypotenuse")
    assert "No diagram on the slide" in result
    assert "draw_design_diagram" in result
    ctx.session.room_io.room.local_participant.publish_data.assert_not_called()


@pytest.mark.asyncio
async def test_bracket_unknown_element_publishes_soft_target() -> None:
    """Phase 1: one missing handle no longer aborts the bracket. Both ends
    are emitted as targets — the frontend resolves each against the live
    DOM, and silently skips the bracket if either end can't be located."""
    ctx = _make_mock_ctx()
    result = await bracket(
        ctx,
        element_a="hypotenuse",  # valid — resolves via dictionary
        element_b="floating_unicorn",  # invalid — falls through as role
        label="right triangle",
    )
    assert "right triangle" in result.lower() or "floating_unicorn" in result
    payload = _published_payload(ctx)
    assert payload["type"] == "bracket"
    assert payload["element_a_id"] == "side_AB"  # dictionary resolved
    assert payload["element_b_id"] == "floating_unicorn"  # raw fallback
    assert payload["target_a"]["kind"] == "id"
    assert payload["target_a"]["value"] == "side_AB"
    assert payload["target_b"]["kind"] == "role"
    assert payload["target_b"]["value"] == "floating_unicorn"


@pytest.mark.asyncio
async def test_annotation_tool_publishes_when_bounds_missing() -> None:
    """Phase 1: backend no longer gates publish on dictionary bounds.
    Bounds come from the live DOM (``getBoundingClientRect``) so a missing
    ``bounds`` field in the dictionary is no longer a blocker — the frontend
    measures the rendered element itself."""
    ctx = _make_mock_ctx()
    ctx.userdata.current_diagram_dictionary["theta-marker"] = {
        "role": "right_angle_marker",
        "semantic": "the right angle marker",
        # no bounds key — frontend will measure live
    }
    result = await pin_label_near(
        ctx,
        element_or_role="right_angle_marker",
        text="90°",
    )
    payload = _published_payload(ctx)
    assert payload["type"] == "pin_label"
    assert payload["target_element_id"] == "theta-marker"
    assert payload["target"]["kind"] == "id"
    assert payload["target"]["value"] == "theta-marker"
    assert "theta-marker" in result


@pytest.mark.asyncio
async def test_draw_callout_resolves_role() -> None:
    ctx = _make_mock_ctx()
    await draw_callout(
        ctx,
        from_element="hypotenuse",
        text="this is the ladder!",
        direction="up-right",
    )
    payload = _published_payload(ctx)
    assert payload["type"] == "draw_callout"
    assert payload["panel"] == "slide"
    assert payload["target_element_id"] == "side_AB"
    assert payload["direction"] == "up-right"


@pytest.mark.asyncio
async def test_bracket_resolves_both_roles() -> None:
    ctx = _make_mock_ctx()
    await bracket(
        ctx,
        element_a="hypotenuse",
        element_b="adjacent",
        label="right triangle",
        side="below",
    )
    payload = _published_payload(ctx)
    assert payload["type"] == "bracket"
    assert payload["panel"] == "slide"
    assert payload["element_a_id"] == "side_AB"
    assert payload["element_b_id"] == "side_AC"
    assert payload["label"] == "right triangle"
    assert payload["side"] == "below"


@pytest.mark.asyncio
async def test_highlight_pulse_resolves_role() -> None:
    ctx = _make_mock_ctx()
    await highlight_pulse(
        ctx,
        element_or_role="opposite",
        duration_ms=1500,
    )
    payload = _published_payload(ctx)
    assert payload["type"] == "highlight_pulse"
    assert payload["panel"] == "slide"
    assert payload["target_element_id"] == "side_BC"
    assert payload["duration_ms"] == 1500


@pytest.mark.asyncio
async def test_pin_label_near_normalizes_invalid_position() -> None:
    """Bad position string falls back to the default 'above'."""
    ctx = _make_mock_ctx()
    await pin_label_near(
        ctx,
        element_or_role="hypotenuse",
        text="hi",
        position="askew",  # not a valid Literal
    )
    payload = _published_payload(ctx)
    assert payload["position"] == "above"
