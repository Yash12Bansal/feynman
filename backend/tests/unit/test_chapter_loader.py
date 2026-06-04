"""Tests for chapter_loader.

`load_chapter_by_id` is exercised against a mock Neo4j driver;
`chapter_context_from_extraction` is the hermetic fixture entry point
and gets unit-tested with a synthetic extraction blob plus a sanity-
check against the committed chapter 47 fixture if it's present.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from feynman.agent.doubt_resolution import (
    ChapterContext,
    chapter_context_from_extraction,
    load_chapter_by_id,
)

_CH47_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "data_pre_compute_v2"
    / "out"
    / "phaseH"
    / "extraction.json"
)


# ── chapter_context_from_extraction (synthetic) ────────────────────────────


def test_from_extraction_filters_topics_and_diagrams_by_chapter():
    extraction = {
        "chapters": [
            {
                "chapter_id": "ch1",
                "title": "Chapter One",
                "topic_ids": ["t1", "t2"],
            },
            {
                "chapter_id": "ch2",
                "title": "Chapter Two",
                "topic_ids": ["t99"],
            },
        ],
        "topics": [
            {"topic_id": "t1", "topic_name": "Velocity", "section_number": "1.1"},
            {"topic_id": "t2", "topic_name": "Acceleration", "section_number": "1.2"},
            {"topic_id": "t99", "topic_name": "Other"},
        ],
        "diagrams": [
            {
                "diagram_id": "d_a",
                "description": "velocity diagram",
                "linked_topic_ids": ["t1"],
            },
            {
                "diagram_id": "d_b",
                "description": "unrelated",
                "linked_topic_ids": ["t99"],
            },
        ],
    }
    ctx = chapter_context_from_extraction(extraction, "ch1")
    assert isinstance(ctx, ChapterContext)
    assert set(ctx.topics) == {"t1", "t2"}
    assert set(ctx.diagrams) == {"d_a"}
    assert ctx.topics["t1"].topic_name == "Velocity"


def test_from_extraction_returns_none_when_chapter_missing():
    extraction = {"chapters": [], "topics": [], "diagrams": []}
    assert chapter_context_from_extraction(extraction, "ghost") is None


def test_from_extraction_populates_presentation_mode():
    """Phase IV: a diagram's presentation_mode flows into DiagramData; a missing
    value defaults to 'overview' (a recap shows the complete figure)."""
    extraction = {
        "chapters": [{"chapter_id": "ch1", "title": "C", "topic_ids": ["t1"]}],
        "topics": [{"topic_id": "t1", "topic_name": "T", "section_number": "1.1"}],
        "diagrams": [
            {
                "diagram_id": "d_build",
                "linked_topic_ids": ["t1"],
                "presentation_mode": "build_up",
            },
            {"diagram_id": "d_default", "linked_topic_ids": ["t1"]},
        ],
    }
    ctx = chapter_context_from_extraction(extraction, "ch1")
    assert ctx is not None
    assert ctx.diagrams["d_build"].presentation_mode == "build_up"
    assert ctx.diagrams["d_default"].presentation_mode == "overview"


# ── load_chapter_by_id (mock Neo4j) ────────────────────────────────────────


@pytest.mark.asyncio
async def test_load_chapter_by_id_returns_none_when_missing():
    """Driver returns no record → loader returns None."""
    result_mock = AsyncMock()
    result_mock.single = AsyncMock(return_value=None)
    session_mock = AsyncMock()
    session_mock.run = AsyncMock(return_value=result_mock)
    session_mock.__aenter__.return_value = session_mock
    session_mock.__aexit__.return_value = None
    driver_mock = AsyncMock()
    driver_mock.session = lambda **kw: session_mock
    driver_mock.close = AsyncMock()

    with patch(
        "feynman.agent.doubt_resolution.chapter_loader.AsyncGraphDatabase.driver",
        return_value=driver_mock,
    ):
        ctx = await load_chapter_by_id("ghost")
    assert ctx is None


@pytest.mark.asyncio
async def test_load_chapter_by_id_hydrates_topics_and_diagrams():
    """Verify the loader maps Neo4j rows into the in-memory ChapterContext."""
    record = {
        "chapter_id": "ch1",
        "title": "Test",
        "topics": [
            {
                "topic_id": "t1",
                "topic_name": "Frames",
                "section_number": "1.1",
                "summary": "Inertial frames.",
            }
        ],
        "diagrams": [
            {
                "diagram_id": "d1",
                "description": "train vs platform",
                "dictionary": json.dumps({"elem1": {"role": "trajectory"}}),
                "linked_topic_ids": ["t1"],
            }
        ],
    }
    result_mock = AsyncMock()
    result_mock.single = AsyncMock(return_value=record)
    session_mock = AsyncMock()
    session_mock.run = AsyncMock(return_value=result_mock)
    session_mock.__aenter__.return_value = session_mock
    session_mock.__aexit__.return_value = None
    driver_mock = AsyncMock()
    driver_mock.session = lambda **kw: session_mock
    driver_mock.close = AsyncMock()

    with patch(
        "feynman.agent.doubt_resolution.chapter_loader.AsyncGraphDatabase.driver",
        return_value=driver_mock,
    ):
        ctx = await load_chapter_by_id("ch1")

    assert ctx is not None
    assert ctx.chapter_id == "ch1"
    assert "t1" in ctx.topics
    assert "d1" in ctx.diagrams
    # dictionary should be JSON-decoded.
    assert ctx.diagrams["d1"].dictionary == {"elem1": {"role": "trajectory"}}
    # presentation_mode absent on the node → defaults to overview.
    assert ctx.diagrams["d1"].presentation_mode == "overview"


# ── Sanity check against the committed Phase H fixture ────────────────────


@pytest.mark.skipif(not _CH47_FIXTURE.exists(), reason="chapter 47 fixture not present")
def test_ch47_fixture_loads_with_topics_and_diagrams():
    extraction = json.loads(_CH47_FIXTURE.read_text())
    # Use whichever chapter id is in the fixture.
    chapter_id = extraction["chapters"][0]["chapter_id"]
    ctx = chapter_context_from_extraction(extraction, chapter_id)
    assert ctx is not None
    assert len(ctx.topics) > 0
    assert len(ctx.diagrams) > 0
