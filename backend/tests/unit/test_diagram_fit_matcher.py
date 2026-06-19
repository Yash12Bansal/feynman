"""Tests for the Phase 4 diagram-fit matcher.

Stage 1 (deterministic TF-IDF + topic-overlap + recency) is tested with
synthetic fixtures. Stage 2 (Haiku verifier) is mocked.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from feynman.agent.doubt_resolution import (
    ChapterContext,
    DiagramData,
    DoubtClassification,
    DoubtType,
    ResolutionBeat,
    ResolutionPlan,
    match_diagrams_for_plan,
)
from feynman.agent.doubt_resolution.diagram_fit_matcher import _stage1_scores


def _diagram(
    diagram_id: str,
    description: str,
    *,
    topics: list[str] | None = None,
    dictionary: dict[str, dict[str, Any]] | None = None,
) -> DiagramData:
    return DiagramData(
        diagram_id=diagram_id,
        description=description,
        dictionary=dictionary or {},
        linked_topic_ids=topics or [],
    )


def _ctx(diagrams: list[DiagramData]) -> ChapterContext:
    return ChapterContext(
        chapter_id="ch1",
        title="Test",
        topics={},
        diagrams={d.diagram_id: d for d in diagrams},
    )


# ── Stage 1: deterministic ─────────────────────────────────────────────────


def test_stage1_text_match_wins():
    ctx = _ctx(
        [
            _diagram("d_train", "A moving train with a ball toss inside"),
            _diagram("d_orbit", "A planet orbiting the sun under gravity"),
        ]
    )
    beat = ResolutionBeat(
        narration_text="here",
        visual_intent_description="ball toss in a train",
    )
    classification = DoubtClassification(type=DoubtType.LOCAL_CLARIFICATION)
    ranked = _stage1_scores(
        doubt_text="why does the ball toss look the same in the moving train?",
        beat=beat,
        chapter_context=ctx,
        classification=classification,
        current_topic_id=None,
        shown_diagram_ids=set(),
    )
    assert ranked[0][0] == "d_train"
    assert ranked[0][1] > ranked[1][1]


def test_stage1_topic_overlap_lifts_score():
    ctx = _ctx(
        [
            _diagram("d_a", "Generic figure", topics=["topic:other"]),
            _diagram("d_b", "Generic figure", topics=["topic:current"]),
        ]
    )
    beat = ResolutionBeat(
        narration_text="x",
        visual_intent_description="some figure",
    )
    classification = DoubtClassification(type=DoubtType.LOCAL_CLARIFICATION)
    ranked = _stage1_scores(
        doubt_text="some doubt",
        beat=beat,
        chapter_context=ctx,
        classification=classification,
        current_topic_id="topic:current",
        shown_diagram_ids=set(),
    )
    assert ranked[0][0] == "d_b"


def test_stage1_recency_penalty_drops_already_shown():
    ctx = _ctx(
        [
            _diagram("d_shown", "A moving train with a ball toss"),
            _diagram("d_fresh", "A moving train with a ball toss"),
        ]
    )
    beat = ResolutionBeat(
        narration_text="x",
        visual_intent_description="ball toss in a train",
    )
    classification = DoubtClassification(type=DoubtType.LOCAL_CLARIFICATION)
    ranked = _stage1_scores(
        doubt_text="ball toss in moving train",
        beat=beat,
        chapter_context=ctx,
        classification=classification,
        current_topic_id=None,
        shown_diagram_ids={"d_shown"},
    )
    assert ranked[0][0] == "d_fresh"


# ── Stage 2: mocked Haiku verifier ─────────────────────────────────────────


def _verdict_response(payload: dict[str, Any]):
    block = SimpleNamespace(type="tool_use", name="emit_fit_verdict", input=payload)
    return SimpleNamespace(content=[block])


@pytest.mark.asyncio
async def test_match_assigns_diagram_when_verifier_accepts():
    ctx = _ctx(
        [
            _diagram("d_train", "A moving train with a ball toss inside"),
            _diagram("d_orbit", "A planet orbiting the sun under gravity"),
        ]
    )
    plan = ResolutionPlan(
        classification={"type": "local_clarification"},
        beats=[
            ResolutionBeat(
                narration_text="The ball moves with the train.",
                visual_intent_description="ball toss in train",
            )
        ],
    )

    create_mock = AsyncMock(
        return_value=_verdict_response(
            {"fits": True, "confidence": 0.9, "rationale": "directly illustrates"}
        )
    )
    client = AsyncMock()
    client.messages = AsyncMock()
    client.messages.create = create_mock

    with patch(
        "feynman.agent.doubt_resolution.diagram_fit_matcher.anthropic.AsyncAnthropic",
        return_value=client,
    ):
        await match_diagrams_for_plan(
            plan=plan,
            chapter_context=ctx,
            doubt_text="why does the ball toss look the same?",
            classification=DoubtClassification(type=DoubtType.LOCAL_CLARIFICATION),
        )

    assert plan.beats[0].target_diagram_id == "d_train"


@pytest.mark.asyncio
async def test_match_leaves_diagram_none_when_verifier_rejects_all():
    ctx = _ctx([_diagram("d_a", "irrelevant"), _diagram("d_b", "also irrelevant")])
    plan = ResolutionPlan(
        classification={"type": "local_clarification"},
        beats=[
            ResolutionBeat(
                narration_text="resolution",
                visual_intent_description="some visual",
            )
        ],
    )
    create_mock = AsyncMock(
        return_value=_verdict_response({"fits": False, "confidence": 0.2, "rationale": "no match"})
    )
    client = AsyncMock()
    client.messages = AsyncMock()
    client.messages.create = create_mock

    with patch(
        "feynman.agent.doubt_resolution.diagram_fit_matcher.anthropic.AsyncAnthropic",
        return_value=client,
    ):
        await match_diagrams_for_plan(
            plan=plan,
            chapter_context=ctx,
            doubt_text="any doubt",
            classification=DoubtClassification(type=DoubtType.LOCAL_CLARIFICATION),
        )

    assert plan.beats[0].target_diagram_id is None


@pytest.mark.asyncio
async def test_match_low_confidence_rejected():
    """confidence < 0.7 → don't assign even if fits=True."""
    ctx = _ctx([_diagram("d_x", "thing")])
    plan = ResolutionPlan(
        classification={"type": "local_clarification"},
        beats=[
            ResolutionBeat(
                narration_text="x",
                visual_intent_description="thing",
            )
        ],
    )
    create_mock = AsyncMock(
        return_value=_verdict_response({"fits": True, "confidence": 0.55, "rationale": "weak"})
    )
    client = AsyncMock()
    client.messages = AsyncMock()
    client.messages.create = create_mock

    with patch(
        "feynman.agent.doubt_resolution.diagram_fit_matcher.anthropic.AsyncAnthropic",
        return_value=client,
    ):
        await match_diagrams_for_plan(
            plan=plan,
            chapter_context=ctx,
            doubt_text="x",
            classification=DoubtClassification(type=DoubtType.LOCAL_CLARIFICATION),
        )

    assert plan.beats[0].target_diagram_id is None


@pytest.mark.asyncio
async def test_match_skip_stage2_uses_top_stage1_above_threshold():
    """The latency escape hatch — no Haiku call, accept top stage-1 if score is decent."""
    ctx = _ctx(
        [
            _diagram("d_train", "A moving train with a ball toss inside", topics=["t1"]),
            _diagram("d_orbit", "A planet orbiting", topics=["t99"]),
        ]
    )
    plan = ResolutionPlan(
        classification={"type": "local_clarification"},
        beats=[
            ResolutionBeat(
                narration_text="ball toss in train",
                visual_intent_description="ball toss in train",
            )
        ],
    )
    classification = DoubtClassification(
        type=DoubtType.LOCAL_CLARIFICATION, related_concept_ids=["t1"]
    )

    client = AsyncMock()
    client.messages = AsyncMock()
    client.messages.create = AsyncMock()  # should never be called

    with patch(
        "feynman.agent.doubt_resolution.diagram_fit_matcher.anthropic.AsyncAnthropic",
        return_value=client,
    ):
        await match_diagrams_for_plan(
            plan=plan,
            chapter_context=ctx,
            doubt_text="ball toss in train",
            classification=classification,
            current_topic_id="t1",
            skip_stage2=True,
        )

    assert plan.beats[0].target_diagram_id == "d_train"
    assert client.messages.create.await_count == 0
