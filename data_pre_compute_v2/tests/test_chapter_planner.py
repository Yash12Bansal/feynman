"""ChapterLecturePlanner smoke tests — happy path + invalid-topic filter."""

from __future__ import annotations

import json
from dataclasses import dataclass


from lecture_pipeline_v2.curriculum.lecture_plan.chapter_planner import (
    ChapterLecturePlanner,
)
from lecture_pipeline_v2.curriculum.lecture_plan.models import ChapterLecturePlan
from lecture_pipeline_v2.curriculum.models import Chapter, Topic
from lecture_pipeline_v2.llm.base import LLMProvider, LLMResponse


@dataclass
class _StubProvider(LLMProvider):
    """Test double that returns a hardcoded LLMResponse."""

    canned_content: str = ""

    def __init__(self, canned_content: str) -> None:
        # Bypass the abstract __init__'s config dependency.
        self.canned_content = canned_content

    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        return LLMResponse(content=self.canned_content, model="stub")

    def generate_json(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        return LLMResponse(content=self.canned_content, model="stub")


def _make_topic(topic_id: str, name: str, section: str) -> Topic:
    return Topic(
        topic_id=topic_id,
        chapter_id="ch_test",
        section_number=section,
        within_chapter_order=int(section.split(".")[-1]),
        topic_name=name,
        orig_book_content=f"Raw text for {name}.",
        our_understanding=f"Plain-English explanation of {name}.",
    )


def _make_chapter() -> Chapter:
    return Chapter(
        chapter_id="ch_test",
        chapter_index=1,
        title="Newton's Laws of Motion",
        summary="Three laws that govern classical motion.",
        page_start=1,
        page_end=20,
        topic_ids=["t1", "t2", "t3"],
    )


def _valid_plan_json(topic_ids: list[str]) -> str:
    return json.dumps(
        {
            "chapter_id": "ch_test",
            "chapter_title": "Newton's Laws of Motion",
            "chapter_arc": "Motion → forces → inertia: three rules.",
            "opening_hook": "Why does a seatbelt save your life?",
            "concept_sequence": topic_ids,
            "coverage_checklist": [
                {
                    "description": "explain inertia from a seatbelt example",
                    "owned_by_topic_id": "t1",
                }
            ],
            "length_budget_seconds": 600,
            "per_concept_budget_seconds": {
                "t1": 200,
                "t2": 200,
                "t3": 200,
            },
            "closing_summary": "Three laws, one common thread: forces explain change in motion.",
        }
    )


def test_chapter_planner_happy_path() -> None:
    topics = [
        _make_topic("t1", "Inertia", "1.1"),
        _make_topic("t2", "F = ma", "1.2"),
        _make_topic("t3", "Action-Reaction", "1.3"),
    ]
    chapter = _make_chapter()

    llm = _StubProvider(canned_content=_valid_plan_json(["t1", "t2", "t3"]))
    planner = ChapterLecturePlanner(llm)
    plans = planner.plan_for_all([chapter], {"ch_test": topics})

    assert "ch_test" in plans
    plan = plans["ch_test"]
    assert isinstance(plan, ChapterLecturePlan)
    assert plan.concept_sequence == ["t1", "t2", "t3"]
    assert plan.length_budget_seconds == 600


def test_chapter_planner_filters_invalid_topic_ids() -> None:
    """LLM occasionally hallucinates a topic id. Planner must drop it."""
    topics = [_make_topic("t1", "Inertia", "1.1"), _make_topic("t2", "F = ma", "1.2")]
    chapter = _make_chapter()
    chapter.topic_ids = ["t1", "t2"]

    llm = _StubProvider(canned_content=_valid_plan_json(["t1", "GHOST_TOPIC", "t2"]))
    planner = ChapterLecturePlanner(llm)
    plans = planner.plan_for_all([chapter], {"ch_test": topics})

    assert plans["ch_test"].concept_sequence == ["t1", "t2"]


def test_chapter_planner_skips_empty_chapter() -> None:
    chapter = _make_chapter()
    llm = _StubProvider(canned_content=_valid_plan_json(["t1"]))
    planner = ChapterLecturePlanner(llm)
    plans = planner.plan_for_all([chapter], {"ch_test": []})
    assert plans == {}


def test_chapter_planner_returns_empty_on_invalid_json() -> None:
    topics = [_make_topic("t1", "Inertia", "1.1")]
    chapter = _make_chapter()
    llm = _StubProvider(canned_content="not valid json {{{")
    planner = ChapterLecturePlanner(llm)
    plans = planner.plan_for_all([chapter], {"ch_test": topics})
    assert plans == {}


def test_chapter_planner_returns_empty_on_schema_violation() -> None:
    topics = [_make_topic("t1", "Inertia", "1.1")]
    chapter = _make_chapter()
    # Missing required fields (length_budget_seconds, closing_summary, etc.)
    bad_payload = json.dumps(
        {
            "chapter_id": "ch_test",
            "chapter_title": "x",
            "concept_sequence": ["t1"],
        }
    )
    llm = _StubProvider(canned_content=bad_payload)
    planner = ChapterLecturePlanner(llm)
    plans = planner.plan_for_all([chapter], {"ch_test": topics})
    assert plans == {}
