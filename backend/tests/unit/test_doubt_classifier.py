"""Tests for the Phase 3 doubt classifier stub.

The stub always returns `local_clarification`; these tests pin the
public surface so Phase 4 can swap the body without breaking callers.
"""

import pytest

from feynman.agent.doubt_resolution import (
    DoubtClassification,
    DoubtType,
    classify_doubt,
)


@pytest.mark.asyncio
async def test_classify_doubt_returns_local_clarification_by_default():
    result = await classify_doubt(doubt_text="why does that happen?")
    assert isinstance(result, DoubtClassification)
    assert result.type == DoubtType.LOCAL_CLARIFICATION
    assert result.related_concept_ids == []
    assert "stub" in result.rationale.lower()


@pytest.mark.asyncio
async def test_classify_doubt_accepts_all_phase4_kwargs():
    """Phase 4 will need the full kwarg surface — verify the stub accepts them."""
    result = await classify_doubt(
        doubt_text="follow-up",
        current_topic_id="topic:physics:1",
        current_topic_context_snippet="snippet",
        prior_doubts_in_session=["earlier doubt"],
    )
    assert result.type == DoubtType.LOCAL_CLARIFICATION
