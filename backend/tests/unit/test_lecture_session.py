"""Integration of classify+plan under LectureDoubtSession.

The planner is one CoT call that classifies AND plans (it emits
`classification` alongside the beats), so each `resolve()` is a single mocked
LLM call. The test exercises the wiring: history gets appended, valid reuse
ids flow into the shown set, and the returned plan is well-formed.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from feynman.agent.doubt_resolution import (
    ChapterContext,
    DiagramData,
    LectureDoubtSession,
    TopicMeta,
)

# The classification the planner now emits as part of its plan. Folded into
# every plan payload below (the merged CoT call returns both).
_CLASSIFICATION = {
    "type": "local_clarification",
    "related_concept_ids": [],
    "rationale": "small clarification about the current topic",
}


def _resp(name: str, payload: dict[str, Any]):
    block = SimpleNamespace(type="tool_use", name=name, input=payload)
    return SimpleNamespace(content=[block])


def _plan(beats: list[dict[str, Any]]) -> Any:
    """A planner tool response: classification + beats, the merged CoT shape."""
    return _resp(
        "emit_resolution_plan",
        {"classification": dict(_CLASSIFICATION), "beats": beats},
    )


def _ctx() -> ChapterContext:
    return ChapterContext(
        chapter_id="ch1",
        title="Test",
        topics={
            "t1": TopicMeta(
                topic_id="t1",
                topic_name="Frames",
                section_number="1.1",
                summary="Inertial frames.",
            )
        },
        diagrams={
            "d1": DiagramData(
                diagram_id="d1",
                description="train vs platform ball toss",
                linked_topic_ids=["t1"],
            )
        },
    )


def _make_client(responses: list[Any]) -> AsyncMock:
    """Single AsyncMock for the planner call(s).

    `anthropic.AsyncAnthropic` is one module attribute regardless of which
    submodule imported it, so patching it once is enough. Each `resolve()` now
    makes exactly ONE planner call (classify + plan merged), so `responses` is
    one entry per resolve (plus retries on failure).
    """
    create_mock = AsyncMock(side_effect=responses)
    client = AsyncMock()
    client.messages = AsyncMock()
    client.messages.create = create_mock
    return client


@pytest.mark.asyncio
async def test_resolve_runs_full_pipeline_and_records_history():
    planner_resp = _plan(
        [
            {
                "narration_text": "Here's the idea.",
                "diagram": {"mode": "reuse", "diagram_id": "d1"},
                "notebook_writes": [],
                "annotation_actions": [],
            }
        ]
    )

    client = _make_client([planner_resp])
    session = LectureDoubtSession(chapter_context=_ctx())

    with patch(
        "feynman.agent.doubt_resolution.resolution_planner.anthropic.AsyncAnthropic",
        return_value=client,
    ):
        plan = await session.resolve(
            doubt_text="why does the ball toss look the same?",
            current_topic_id="t1",
            cursor=42,
        )

    assert plan is not None
    assert len(plan.beats) == 1
    assert plan.beats[0].target_diagram_id == "d1"
    # Classification now rides on the plan.
    assert plan.classification.type.value == "local_clarification"

    assert len(session.prior_doubts_in_session) == 1
    assert session.prior_doubts_in_session[0].doubt_text == (
        "why does the ball toss look the same?"
    )
    assert "d1" in session.shown_diagram_ids


@pytest.mark.asyncio
async def test_resolve_returns_none_when_planner_fails():
    # Both planner attempts fail → no plan, no history.
    client = _make_client([RuntimeError("fail"), RuntimeError("again")])
    session = LectureDoubtSession(chapter_context=_ctx())

    with patch(
        "feynman.agent.doubt_resolution.resolution_planner.anthropic.AsyncAnthropic",
        return_value=client,
    ):
        plan = await session.resolve(doubt_text="x", current_topic_id="t1")

    assert plan is None
    assert session.prior_doubts_in_session == []


@pytest.mark.asyncio
async def test_resolve_accumulates_prior_doubts_across_calls():
    """Three doubts in a row → prior_doubts_in_session grows to 3. One planner
    call per doubt now (classify + plan merged)."""
    beats = [
        {
            "narration_text": "Here's the idea — for this doubt.",
            "visual_intent_description": "",
            "annotation_actions": [],
            "target_diagram_id": None,
        }
    ]
    responses = [_plan(beats) for _ in range(3)]
    client = _make_client(responses)
    session = LectureDoubtSession(chapter_context=_ctx())

    with patch(
        "feynman.agent.doubt_resolution.resolution_planner.anthropic.AsyncAnthropic",
        return_value=client,
    ):
        await session.resolve(doubt_text="doubt one", current_topic_id="t1")
        await session.resolve(doubt_text="doubt two", current_topic_id="t1")
        await session.resolve(doubt_text="doubt three", current_topic_id="t1")

    assert len(session.prior_doubts_in_session) == 3
    assert [r.doubt_text for r in session.prior_doubts_in_session] == [
        "doubt one",
        "doubt two",
        "doubt three",
    ]


@pytest.mark.asyncio
async def test_resolve_validates_reuse_id():
    """The planner decides the diagram; resolve() validates reuse picks against
    the real chapter diagrams — a hallucinated id degrades to NoDiagram, a real
    one is mirrored to target_diagram_id + the recency set."""
    planner_resp = _plan(
        [
            {
                "narration_text": "Here's what's happening, step by step.",
                "diagram": {"mode": "reuse", "diagram_id": "d1"},
                "notebook_writes": [],
                "annotation_actions": [],
            },
            {
                "narration_text": "And that explains the rest of it.",
                "diagram": {"mode": "reuse", "diagram_id": "ghost"},
                "notebook_writes": [],
                "annotation_actions": [],
            },
        ]
    )
    client = _make_client([planner_resp])
    session = LectureDoubtSession(chapter_context=_ctx())

    with patch(
        "feynman.agent.doubt_resolution.resolution_planner.anthropic.AsyncAnthropic",
        return_value=client,
    ):
        plan = await session.resolve(doubt_text="what does inertial mean?", current_topic_id="t1")

    assert plan is not None
    # valid reuse → mirrored to target_diagram_id
    assert plan.beats[0].target_diagram_id == "d1"
    # invalid reuse → degraded to NoDiagram, no target
    assert plan.beats[1].diagram.mode == "none"
    assert plan.beats[1].target_diagram_id is None
    assert session.shown_diagram_ids == {"d1"}


@pytest.mark.asyncio
async def test_resolve_degrades_unknown_template():
    """A `template` directive with an invented concept_id degrades to NoDiagram
    (the narration still answers); a known canonical id is left intact."""
    planner_resp = _plan(
        [
            {
                "narration_text": "Picture the right triangle for this.",
                "diagram": {"mode": "template", "concept_id": "right-triangle-trig"},
                "notebook_writes": [],
                "annotation_actions": [],
            },
            {
                "narration_text": "And that ties it together.",
                "diagram": {"mode": "template", "concept_id": "not-a-real-template"},
                "notebook_writes": [],
                "annotation_actions": [],
            },
        ]
    )
    client = _make_client([planner_resp])
    session = LectureDoubtSession(chapter_context=_ctx())

    with patch(
        "feynman.agent.doubt_resolution.resolution_planner.anthropic.AsyncAnthropic",
        return_value=client,
    ):
        plan = await session.resolve(doubt_text="how do I find the angle?", current_topic_id="t1")

    assert plan is not None
    # known template id is kept; unknown id degrades to no-diagram.
    assert plan.beats[0].diagram.mode == "template"
    assert plan.beats[0].diagram.concept_id == "right-triangle-trig"
    assert plan.beats[1].diagram.mode == "none"
