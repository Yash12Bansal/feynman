"""Integration of classifier → planner → matcher under LectureDoubtSession.

All three LLM stages are mocked; the test exercises the wiring: history
gets appended, shown diagrams flow into the matcher, and the returned
plan is well-formed.
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


def _resp(name: str, payload: dict[str, Any]):
    block = SimpleNamespace(type="tool_use", name=name, input=payload)
    return SimpleNamespace(content=[block])


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
    """Single AsyncMock shared across all three pipeline stages.

    `anthropic.AsyncAnthropic` is one module attribute regardless of which
    submodule imported it, so a single patch is enough — but the side
    effects must be sequenced in invocation order: classifier → planner
    → matcher (which calls Haiku per beat).
    """
    create_mock = AsyncMock(side_effect=responses)
    client = AsyncMock()
    client.messages = AsyncMock()
    client.messages.create = create_mock
    return client


@pytest.mark.asyncio
async def test_resolve_runs_full_pipeline_and_records_history():
    classifier_resp = _resp(
        "emit_classification",
        {
            "type": "local_clarification",
            "related_concept_ids": [],
            "rationale": "stub",
        },
    )
    planner_resp = _resp(
        "emit_resolution_plan",
        {
            "beats": [
                {
                    "narration_text": "Here's the idea.",
                    "visual_intent_description": "train vs platform",
                    "annotation_actions": [],
                    "target_diagram_id": None,
                }
            ]
        },
    )
    matcher_resp = _resp(
        "emit_fit_verdict",
        {"fits": True, "confidence": 0.9, "rationale": "yes"},
    )

    client = _make_client([classifier_resp, planner_resp, matcher_resp])
    session = LectureDoubtSession(chapter_context=_ctx())

    with patch(
        "feynman.agent.doubt_resolution.doubt_classifier.anthropic.AsyncAnthropic",
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

    assert len(session.prior_doubts_in_session) == 1
    assert session.prior_doubts_in_session[0].doubt_text == (
        "why does the ball toss look the same?"
    )
    assert "d1" in session.shown_diagram_ids


@pytest.mark.asyncio
async def test_resolve_returns_none_when_planner_fails():
    classifier_resp = _resp(
        "emit_classification",
        {"type": "local_clarification", "related_concept_ids": [], "rationale": "ok"},
    )
    client = _make_client(
        [
            classifier_resp,
            RuntimeError("fail"),
            RuntimeError("again"),
        ]
    )
    session = LectureDoubtSession(chapter_context=_ctx())

    with patch(
        "feynman.agent.doubt_resolution.doubt_classifier.anthropic.AsyncAnthropic",
        return_value=client,
    ):
        plan = await session.resolve(doubt_text="x", current_topic_id="t1")

    assert plan is None
    # No history recorded when the planner fails.
    assert session.prior_doubts_in_session == []
