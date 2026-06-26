"""Persona → lesson planner prompt equivalence tests."""

from __future__ import annotations

from pathlib import Path

from feynman_teaching_kernel.persona import format_style_for_planner
from feynman_teaching_kernel.persona_registry import load_persona
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_planner import (
    _build_user_message,
)
from lecture_pipeline_v2.curriculum.lecture_plan.curriculum_adapter import (
    CurriculumAdapter,
)
from lecture_pipeline_v2.curriculum.lecture_plan.models import ChapterLecturePlan
from lecture_pipeline_v2.curriculum.models import Chapter, Topic

PERSONAS_DIR = Path(__file__).resolve().parents[1] / "personas"
STYLE_MD = Path(__file__).resolve().parents[1] / "feynman_special_relativity_style.md"


def _minimal_adapter() -> CurriculumAdapter:
    chapter = Chapter(
        chapter_id="ch1",
        chapter_index=1,
        title="Relativity",
        summary="s",
        page_start=1,
        page_end=10,
        topic_ids=["t1"],
    )
    topic = Topic(
        topic_id="t1",
        chapter_id="ch1",
        section_number="15.1",
        within_chapter_order=1,
        topic_name="Time dilation",
        orig_book_content="text",
        our_understanding="clocks run slow when moving",
    )
    plan = ChapterLecturePlan(
        chapter_id="ch1",
        chapter_title="Relativity",
        chapter_arc="arc",
        opening_hook="hook",
        concept_sequence=["t1"],
        length_budget_seconds=600,
        closing_summary="close",
    )
    return CurriculumAdapter(chapter, [topic], plan, {})


def test_feynman_persona_matches_style_markdown_in_planner_prompt() -> None:
    persona = load_persona("feynman", PERSONAS_DIR)
    persona_style = format_style_for_planner(persona)
    assert persona_style is not None

    markdown_style = STYLE_MD.read_text(encoding="utf-8")

    msg_from_persona = _build_user_message(
        concept_index=0,
        curriculum=_minimal_adapter(),
        topic_id="t1",
        prior_validation_error=None,
        style_context=persona_style,
    )
    msg_from_md = _build_user_message(
        concept_index=0,
        curriculum=_minimal_adapter(),
        topic_id="t1",
        prior_validation_error=None,
        style_context=markdown_style[:6000],
    )

    # Core Feynman voice markers must appear in both paths.
    for needle in ("Michelson", "light clock", "physical intuition"):
        assert needle.lower() in msg_from_persona.lower()
        assert needle.lower() in msg_from_md.lower()

    assert "## Master-teacher style" in msg_from_persona
    assert "Figure preference: reproduce_named_figures" in msg_from_persona
