"""Tests for the Phase 4 ResolutionPlanner.

Mocked Anthropic. Verifies the planner serialises the right context into
the request, validates the response into a `ResolutionPlan`, and applies
the `different_angle` flag.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from feynman.agent.doubt_resolution import (
    ChapterContext,
    DiagramData,
    ResolutionPlan,
    TopicMeta,
    plan_resolution,
)


def _plan_response(payload: dict[str, Any]):
    block = SimpleNamespace(type="tool_use", name="emit_resolution_plan", input=payload)
    return SimpleNamespace(content=[block])


def _ctx() -> ChapterContext:
    return ChapterContext(
        chapter_id="ch1",
        title="Special Relativity",
        topics={
            "t1": TopicMeta(
                topic_id="t1",
                topic_name="Principle of Relativity",
                section_number="1.1",
                summary="Physics looks identical in all inertial frames.",
            ),
            "t2": TopicMeta(
                topic_id="t2",
                topic_name="Inertial frames",
                section_number="1.2",
                summary="Frames in uniform motion.",
            ),
        },
        diagrams={
            "d1": DiagramData(
                diagram_id="d1",
                description="Side by side: ball toss on platform vs in train",
                linked_topic_ids=["t1"],
            )
        },
    )


_CLASSIFICATION = {
    "type": "local_clarification",
    "related_concept_ids": [],
    "rationale": "small clarification about the current topic",
}


def _valid_plan_payload() -> dict[str, Any]:
    return {
        "classification": dict(_CLASSIFICATION),
        "beats": [
            {
                "narration_text": "Here's what's happening: in any inertial frame, the physics is identical.",
                "visual_intent_description": "side-by-side comparison",
                "annotation_actions": [
                    {"action": "focus", "target_role": "trajectory", "text": "look here"}
                ],
                "target_diagram_id": None,
            },
            {
                "narration_text": "The ball's path looks vertical in the train and curved on the platform.",
                "visual_intent_description": "trace the two paths",
                "annotation_actions": [],
                "target_diagram_id": None,
            },
        ],
    }


@pytest.mark.asyncio
async def test_plan_resolution_returns_valid_plan():
    create_mock = AsyncMock(return_value=_plan_response(_valid_plan_payload()))
    client = AsyncMock()
    client.messages = AsyncMock()
    client.messages.create = create_mock

    with patch(
        "feynman.agent.doubt_resolution.resolution_planner.anthropic.AsyncAnthropic",
        return_value=client,
    ):
        plan = await plan_resolution(
            doubt_text="why does the ball toss look the same?",
            chapter_context=_ctx(),
            current_topic_id="t1",
        )

    assert isinstance(plan, ResolutionPlan)
    assert len(plan.beats) == 2
    assert plan.beats[0].annotation_actions[0].action == "focus"
    assert all(b.target_diagram_id is None for b in plan.beats)


@pytest.mark.asyncio
async def test_plan_resolution_includes_topic_context_in_prompt():
    create_mock = AsyncMock(return_value=_plan_response(_valid_plan_payload()))
    client = AsyncMock()
    client.messages = AsyncMock()
    client.messages.create = create_mock

    with patch(
        "feynman.agent.doubt_resolution.resolution_planner.anthropic.AsyncAnthropic",
        return_value=client,
    ):
        await plan_resolution(
            doubt_text="why?",
            chapter_context=_ctx(),
            current_topic_id="t1",
        )

    call_kwargs = create_mock.await_args.kwargs
    content = call_kwargs["messages"][0]["content"]
    assert "Principle of Relativity" in content
    # Diagrams should appear so the planner knows what's available.
    assert "d1" in content
    # Adjacent topic should be referenced.
    assert "Inertial frames" in content


@pytest.mark.asyncio
async def test_plan_resolution_different_angle_emits_replanning_instruction():
    create_mock = AsyncMock(return_value=_plan_response(_valid_plan_payload()))
    client = AsyncMock()
    client.messages = AsyncMock()
    client.messages.create = create_mock

    with patch(
        "feynman.agent.doubt_resolution.resolution_planner.anthropic.AsyncAnthropic",
        return_value=client,
    ):
        await plan_resolution(
            doubt_text="why?",
            chapter_context=_ctx(),
            current_topic_id="t1",
            different_angle=True,
            prior_resolution_summary="earlier explanation used a train analogy",
        )

    content = create_mock.await_args.kwargs["messages"][0]["content"]
    assert "RE-PLAN" in content
    assert "train analogy" in content


@pytest.mark.asyncio
async def test_plan_resolution_returns_none_after_two_failures():
    create_mock = AsyncMock(side_effect=[RuntimeError("boom"), RuntimeError("still boom")])
    client = AsyncMock()
    client.messages = AsyncMock()
    client.messages.create = create_mock

    with patch(
        "feynman.agent.doubt_resolution.resolution_planner.anthropic.AsyncAnthropic",
        return_value=client,
    ):
        plan = await plan_resolution(
            doubt_text="x",
            chapter_context=_ctx(),
        )
    assert plan is None


@pytest.mark.asyncio
async def test_plan_resolution_recovers_on_retry_after_validation_error():
    bad = {"classification": dict(_CLASSIFICATION), "beats": []}  # min_length=1 → ValidationError
    good = _valid_plan_payload()
    create_mock = AsyncMock(side_effect=[_plan_response(bad), _plan_response(good)])
    client = AsyncMock()
    client.messages = AsyncMock()
    client.messages.create = create_mock

    with patch(
        "feynman.agent.doubt_resolution.resolution_planner.anthropic.AsyncAnthropic",
        return_value=client,
    ):
        plan = await plan_resolution(
            doubt_text="x",
            chapter_context=_ctx(),
        )

    assert plan is not None
    assert create_mock.await_count == 2


@pytest.mark.asyncio
async def test_plan_resolution_rejects_banned_opener_and_retries():
    """Phase 6: a beat opening with 'Great question!' triggers Pydantic
    validation; the planner's 2-attempt retry catches it + re-prompts.
    """
    bad = {
        "classification": dict(_CLASSIFICATION),
        "beats": [
            {
                "narration_text": "Great question! Let me explain the idea.",
                "visual_intent_description": "x",
                "annotation_actions": [],
                "target_diagram_id": None,
            }
        ],
    }
    good = _valid_plan_payload()
    create_mock = AsyncMock(side_effect=[_plan_response(bad), _plan_response(good)])
    client = AsyncMock()
    client.messages = AsyncMock()
    client.messages.create = create_mock

    with patch(
        "feynman.agent.doubt_resolution.resolution_planner.anthropic.AsyncAnthropic",
        return_value=client,
    ):
        plan = await plan_resolution(
            doubt_text="why?",
            chapter_context=_ctx(),
        )

    assert plan is not None
    assert create_mock.await_count == 2
    assert not plan.beats[0].narration_text.lower().startswith("great question")


@pytest.mark.asyncio
async def test_plan_resolution_accepts_directive_and_notebook_shape():
    """The planner now decides the diagram (reuse/generate) and writes notebook
    lines directly — no downstream matcher in the planning path."""
    payload = {
        "classification": dict(_CLASSIFICATION),
        "beats": [
            {
                "narration_text": "Here's the piece that's off: the speed carries over.",
                "diagram": {"mode": "reuse", "diagram_id": "d1"},
                "notebook_writes": [
                    {"block": "step", "text": "ball speed = train + toss"},
                    {"block": "equation", "latex": "v = u + at", "boxed": True},
                ],
                "annotation_actions": [
                    {"action": "focus", "target_element_id": "arc", "text": "here"}
                ],
            },
            {
                "narration_text": "From the platform the path bends into an arc.",
                "diagram": {
                    "mode": "generate",
                    "brief": "a parabola seen from the platform frame",
                    "title": "Platform",
                },
                "notebook_writes": [],
                "annotation_actions": [],
            },
        ],
    }
    create_mock = AsyncMock(return_value=_plan_response(payload))
    client = AsyncMock()
    client.messages = AsyncMock()
    client.messages.create = create_mock

    with patch(
        "feynman.agent.doubt_resolution.resolution_planner.anthropic.AsyncAnthropic",
        return_value=client,
    ):
        plan = await plan_resolution(
            doubt_text="why is it the same?",
            chapter_context=_ctx(),
            current_topic_id="t1",
        )

    assert plan is not None
    assert plan.beats[0].diagram.mode == "reuse"
    assert plan.beats[0].diagram.diagram_id == "d1"
    assert len(plan.beats[0].notebook_writes) == 2
    assert plan.beats[1].diagram.mode == "generate"
    assert plan.beats[1].diagram.brief
