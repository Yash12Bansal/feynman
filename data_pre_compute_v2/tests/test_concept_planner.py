"""ConceptPlanner — verifies kernel-call flow + single-retry semantics.

The kernel's plan_concept is monkey-patched so tests don't hit the real
Anthropic API.
"""

from __future__ import annotations

from typing import Any

import pytest
from feynman_teaching_kernel import ConceptTeachingPlan, TeachingBeat

from lecture_pipeline_v2.config import LLMConfig, PipelineConfig
from lecture_pipeline_v2.curriculum.lecture_plan.concept_planner import ConceptPlanner
from lecture_pipeline_v2.curriculum.lecture_plan.models import ChapterLecturePlan
from lecture_pipeline_v2.curriculum.models import Chapter, Topic


def _config() -> PipelineConfig:
    return PipelineConfig(
        llm=LLMConfig(api_key="test-key", model="claude-sonnet-4-test")
    )


def _chapter() -> Chapter:
    return Chapter(
        chapter_id="ch1",
        chapter_index=1,
        title="Chapter X",
        summary="s",
        page_start=1,
        page_end=10,
        topic_ids=["t1", "t2"],
    )


def _topic(topic_id: str, name: str) -> Topic:
    return Topic(
        topic_id=topic_id,
        chapter_id="ch1",
        section_number="1.1",
        within_chapter_order=1,
        topic_name=name,
        orig_book_content="raw text",
        our_understanding="understanding",
    )


def _lecture_plan(seq: list[str]) -> ChapterLecturePlan:
    return ChapterLecturePlan(
        chapter_id="ch1",
        chapter_title="Chapter X",
        chapter_arc="arc",
        opening_hook="hook",
        concept_sequence=seq,
        length_budget_seconds=600,
        closing_summary="close",
    )


def _arc_plan(concept_index: int, title: str) -> ConceptTeachingPlan:
    return ConceptTeachingPlan(
        concept_title=title,
        concept_index=concept_index,
        opening_hook="o",
        core_analogy="a",
        prerequisite_bridge="p",
        beats=[
            TeachingBeat(beat_type="hook", speech_guidance="hook"),
            TeachingBeat(beat_type="big_picture", speech_guidance="big"),
            TeachingBeat(beat_type="first_principles", speech_guidance="first"),
        ],
        board_pattern="concept_intro",
        visual_narrative="v",
    )


@pytest.mark.asyncio
async def test_concept_planner_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """One plan per topic in concept_sequence; prev_plan threads through."""
    call_log: list[tuple[int, str, str | None]] = []

    async def fake_plan_concept(
        concept_index: int,
        curriculum: Any,
        plan: Any,
        *,
        board_summary: str = "",
        audit: Any = None,
        prev_plan: ConceptTeachingPlan | None = None,
        allowed_visual_tools: list[str] | None = None,
        api_key: str,
        model: str,
    ) -> ConceptTeachingPlan:
        concept = curriculum.get_teaching_order()[concept_index]
        prev_title = prev_plan.concept_title if prev_plan else None
        call_log.append((concept_index, concept.topic_name, prev_title))
        return _arc_plan(concept_index, concept.topic_name)

    monkeypatch.setattr(
        "lecture_pipeline_v2.curriculum.lecture_plan.concept_planner.plan_concept",
        fake_plan_concept,
    )

    planner = ConceptPlanner(_config())
    result = await planner.plan_for_all(
        [_chapter()],
        {"ch1": [_topic("t1", "Topic One"), _topic("t2", "Topic Two")]},
        {"ch1": _lecture_plan(["t1", "t2"])},
        {},
    )

    plans = result["ch1"]
    assert [p.concept_title for p in plans] == ["Topic One", "Topic Two"]
    # prev_plan threads: first call gets None, second gets the first plan.
    assert call_log[0] == (0, "Topic One", None)
    assert call_log[1] == (1, "Topic Two", "Topic One")


@pytest.mark.asyncio
async def test_concept_planner_retries_on_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the kernel returns None first call, planner retries once."""
    call_count = {"n": 0}

    async def flaky_plan_concept(
        concept_index: int,
        curriculum: Any,
        plan: Any,
        *,
        board_summary: str = "",
        audit: Any = None,
        prev_plan: ConceptTeachingPlan | None = None,
        allowed_visual_tools: list[str] | None = None,
        api_key: str,
        model: str,
    ) -> ConceptTeachingPlan | None:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return None
        return _arc_plan(concept_index, "Topic One")

    monkeypatch.setattr(
        "lecture_pipeline_v2.curriculum.lecture_plan.concept_planner.plan_concept",
        flaky_plan_concept,
    )

    planner = ConceptPlanner(_config())
    result = await planner.plan_for_all(
        [_chapter()],
        {"ch1": [_topic("t1", "Topic One")]},
        {"ch1": _lecture_plan(["t1"])},
        {},
    )

    assert call_count["n"] == 2
    assert len(result["ch1"]) == 1
    assert result["ch1"][0].concept_title == "Topic One"


@pytest.mark.asyncio
async def test_concept_planner_gives_up_after_second_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two consecutive None returns → drop that topic, keep going."""
    call_count = {"n": 0}

    async def always_none(*args, **kwargs) -> None:
        call_count["n"] += 1
        return None

    monkeypatch.setattr(
        "lecture_pipeline_v2.curriculum.lecture_plan.concept_planner.plan_concept",
        always_none,
    )

    planner = ConceptPlanner(_config())
    result = await planner.plan_for_all(
        [_chapter()],
        {"ch1": [_topic("t1", "Topic One")]},
        {"ch1": _lecture_plan(["t1"])},
        {},
    )

    # 1 topic × 2 attempts each = 2 calls
    assert call_count["n"] == 2
    # Failed concept produces no plan — but the chapter still gets an empty list.
    assert result["ch1"] == []


@pytest.mark.asyncio
async def test_concept_planner_skips_chapter_without_lecture_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If ChapterLecturePlanner failed for a chapter, ConceptPlanner skips it."""
    called = False

    async def should_not_be_called(*args, **kwargs):
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(
        "lecture_pipeline_v2.curriculum.lecture_plan.concept_planner.plan_concept",
        should_not_be_called,
    )

    planner = ConceptPlanner(_config())
    result = await planner.plan_for_all(
        [_chapter()],
        {"ch1": [_topic("t1", "Topic One")]},
        {},  # no lecture plan
        {},
    )

    assert called is False
    assert result == {}


@pytest.mark.asyncio
async def test_concept_planner_passes_allowed_visual_tools_to_kernel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Doc 18 §5.2: v2 always passes its allowed_visual_tools whitelist."""
    captured: dict[str, Any] = {}

    async def capture(
        concept_index: int,
        curriculum: Any,
        plan: Any,
        *,
        board_summary: str = "",
        audit: Any = None,
        prev_plan: ConceptTeachingPlan | None = None,
        allowed_visual_tools: list[str] | None = None,
        api_key: str,
        model: str,
    ) -> ConceptTeachingPlan:
        captured["allowed_visual_tools"] = allowed_visual_tools
        return _arc_plan(concept_index, "Topic One")

    monkeypatch.setattr(
        "lecture_pipeline_v2.curriculum.lecture_plan.concept_planner.plan_concept",
        capture,
    )

    planner = ConceptPlanner(_config())
    await planner.plan_for_all(
        [_chapter()],
        {"ch1": [_topic("t1", "Topic One")]},
        {"ch1": _lecture_plan(["t1"])},
        {},
    )

    tools = captured["allowed_visual_tools"]
    assert tools is not None
    assert "draw_design_diagram" in tools
    assert "modify_design_diagram" in tools
    # Notebook tools also in whitelist.
    assert "write_equation" in tools
    assert "write_step" in tools
    # Tools NOT in the whitelist:
    assert "draw_scene" not in tools
    assert "draw_diagram" not in tools


# Doc 19 §10: the doc-18 post-plan rewrite (`_enforce_concept_beat_diagrams`)
# was rolled back — quantity of diagrams was the wrong direction. The three
# tests that pinned the rewrite behavior live in git history if needed; they
# don't belong here anymore. The kernel-side `allowed_visual_tools` constraint
# is still tested by `test_concept_planner_passes_allowed_visual_tools_to_kernel`
# above.


@pytest.mark.asyncio
async def test_concept_planner_catches_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defensive: an unexpected exception is caught at the boundary."""
    call_count = {"n": 0}

    async def raises(*args, **kwargs):
        call_count["n"] += 1
        raise RuntimeError("kernel exploded")

    monkeypatch.setattr(
        "lecture_pipeline_v2.curriculum.lecture_plan.concept_planner.plan_concept",
        raises,
    )

    planner = ConceptPlanner(_config())
    result = await planner.plan_for_all(
        [_chapter()],
        {"ch1": [_topic("t1", "Topic One")]},
        {"ch1": _lecture_plan(["t1"])},
        {},
    )

    # Two attempts (one retry), both raise; result is empty.
    assert call_count["n"] == 2
    assert result["ch1"] == []
