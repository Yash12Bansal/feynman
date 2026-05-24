"""Tests for the Phase 4 doubt classifier.

We mock `anthropic.AsyncAnthropic` so the tests are hermetic. Each test
constructs a fake tool-use response, validates that the classifier
deserialises it into `DoubtClassification`, and that retry + fallback
paths behave as designed.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from feynman.agent.doubt_resolution import (
    ChapterContext,
    DoubtClassification,
    DoubtType,
    TopicMeta,
    classify_doubt,
)


def _fake_tool_response(payload: dict[str, Any]):
    """Build a minimal stand-in for anthropic's `Message.content` list."""

    block = SimpleNamespace(type="tool_use", name="emit_classification", input=payload)
    return SimpleNamespace(content=[block])


def _patch_anthropic(payloads_in_order: list[dict[str, Any] | Exception]) -> AsyncMock:
    """Return an AsyncMock whose `messages.create` yields the given payloads."""
    create_mock = AsyncMock()
    side_effects: list[Any] = []
    for p in payloads_in_order:
        if isinstance(p, Exception):
            side_effects.append(p)
        else:
            side_effects.append(_fake_tool_response(p))
    create_mock.side_effect = side_effects

    client_mock = AsyncMock()
    client_mock.messages = AsyncMock()
    client_mock.messages.create = create_mock

    return client_mock


@pytest.mark.asyncio
async def test_classify_doubt_local_clarification():
    client = _patch_anthropic(
        [
            {
                "type": "local_clarification",
                "related_concept_ids": [],
                "rationale": "asking what 'inertial' means",
            }
        ]
    )
    with patch(
        "feynman.agent.doubt_resolution.doubt_classifier.anthropic.AsyncAnthropic",
        return_value=client,
    ):
        result = await classify_doubt(doubt_text="What does inertial frame mean?")
    assert isinstance(result, DoubtClassification)
    assert result.type == DoubtType.LOCAL_CLARIFICATION


@pytest.mark.asyncio
async def test_classify_doubt_interconnected_with_related_topics():
    client = _patch_anthropic(
        [
            {
                "type": "interconnected",
                "related_concept_ids": ["topic:physics:newton"],
                "rationale": "links to Newton's second law",
            }
        ]
    )
    with patch(
        "feynman.agent.doubt_resolution.doubt_classifier.anthropic.AsyncAnthropic",
        return_value=client,
    ):
        result = await classify_doubt(
            doubt_text="How does this connect to Newton's second law?",
            current_topic_id="topic:physics:relativity:1",
        )
    assert result.type == DoubtType.INTERCONNECTED
    assert result.related_concept_ids == ["topic:physics:newton"]


@pytest.mark.asyncio
async def test_classify_doubt_new_angle():
    client = _patch_anthropic(
        [
            {
                "type": "new_angle",
                "related_concept_ids": [],
                "rationale": "fresh hypothetical",
            }
        ]
    )
    with patch(
        "feynman.agent.doubt_resolution.doubt_classifier.anthropic.AsyncAnthropic",
        return_value=client,
    ):
        result = await classify_doubt(doubt_text="What about gravity in a moving train?")
    assert result.type == DoubtType.NEW_ANGLE


@pytest.mark.asyncio
async def test_classify_doubt_retries_on_validation_error_then_succeeds():
    # First payload is invalid (missing required `type`); second is valid.
    client = _patch_anthropic(
        [
            {"related_concept_ids": [], "rationale": "missing type"},
            {
                "type": "local_clarification",
                "related_concept_ids": [],
                "rationale": "valid on retry",
            },
        ]
    )
    with patch(
        "feynman.agent.doubt_resolution.doubt_classifier.anthropic.AsyncAnthropic",
        return_value=client,
    ):
        result = await classify_doubt(doubt_text="huh?")
    assert result.type == DoubtType.LOCAL_CLARIFICATION
    assert client.messages.create.await_count == 2


@pytest.mark.asyncio
async def test_classify_doubt_falls_back_after_two_failures():
    client = _patch_anthropic(
        [
            RuntimeError("API down"),
            RuntimeError("still down"),
        ]
    )
    with patch(
        "feynman.agent.doubt_resolution.doubt_classifier.anthropic.AsyncAnthropic",
        return_value=client,
    ):
        result = await classify_doubt(doubt_text="anything")
    # Fallback is LOCAL_CLARIFICATION with `classifier_failed:` rationale.
    assert result.type == DoubtType.LOCAL_CLARIFICATION
    assert "classifier_failed" in result.rationale


@pytest.mark.asyncio
async def test_classify_doubt_empty_text_returns_default_without_calling_api():
    client = _patch_anthropic([])  # no responses queued
    with patch(
        "feynman.agent.doubt_resolution.doubt_classifier.anthropic.AsyncAnthropic",
        return_value=client,
    ):
        result = await classify_doubt(doubt_text="   ")
    assert result.type == DoubtType.LOCAL_CLARIFICATION
    assert client.messages.create.await_count == 0


@pytest.mark.asyncio
async def test_classify_doubt_includes_chapter_topics_in_prompt():
    """Verify the request body carries the chapter's topic list."""
    client = _patch_anthropic(
        [
            {
                "type": "local_clarification",
                "related_concept_ids": [],
                "rationale": "ok",
            }
        ]
    )
    chapter = ChapterContext(
        chapter_id="ch1",
        title="Test",
        topics={
            "t1": TopicMeta(topic_id="t1", topic_name="Velocity", section_number="1.1"),
            "t2": TopicMeta(topic_id="t2", topic_name="Acceleration", section_number="1.2"),
        },
    )
    with patch(
        "feynman.agent.doubt_resolution.doubt_classifier.anthropic.AsyncAnthropic",
        return_value=client,
    ):
        await classify_doubt(doubt_text="why?", chapter_context=chapter)

    call_kwargs = client.messages.create.await_args.kwargs
    user_content = call_kwargs["messages"][0]["content"]
    assert "Velocity" in user_content
    assert "Acceleration" in user_content
