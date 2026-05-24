"""BeatNarrationWriter (Phase 4d) — per-beat narration smoke tests."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from feynman_teaching_kernel import ConceptTeachingPlan, TeachingBeat, VisualBeatAction

from lecture_pipeline_v2.config import BeatNarrationConfig
from lecture_pipeline_v2.curriculum.beat_narration.writer import (
    BeatNarrationWriter,
    _estimate_seconds,
    _extract_audio_targets,
    _strip_markdown_fence,
)
from lecture_pipeline_v2.curriculum.models import (
    Chapter,
    Diagram,
    DiagramRenderer,
    Topic,
)
from lecture_pipeline_v2.curriculum.lecture_plan.models import ChapterLecturePlan
from lecture_pipeline_v2.llm.base import LLMProvider, LLMResponse


# ---------------------------------------------------------------------------
# Stubs + fixtures
# ---------------------------------------------------------------------------


class _Boom(Exception):
    """Marker exception so we can distinguish stub-raises from real ones."""


@dataclass
class _StubProvider(LLMProvider):
    canned_texts: list[str]
    captured_prompts: list[tuple[str, str]]
    raise_on_call: bool = False

    def __init__(
        self,
        canned_texts: list[str],
        *,
        raise_on_call: bool = False,
    ) -> None:
        self.canned_texts = list(canned_texts)
        self.captured_prompts = []
        self.raise_on_call = raise_on_call

    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        self.captured_prompts.append((system_prompt, user_prompt))
        if self.raise_on_call:
            raise _Boom("stub boom")
        if len(self.canned_texts) > 1:
            content = self.canned_texts.pop(0)
        else:
            content = self.canned_texts[0] if self.canned_texts else ""
        return LLMResponse(content=content, model="stub")

    def generate_json(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        return self.generate(system_prompt, user_prompt)


def _topic(topic_id: str = "t1", name: str = "Pythagoras") -> Topic:
    return Topic(
        topic_id=topic_id,
        chapter_id="ch1",
        section_number="1.1",
        within_chapter_order=1,
        topic_name=name,
        orig_book_content="raw text",
        our_understanding="A right triangle has a^2+b^2=c^2.",
    )


def _arc_plan(concept_index: int, *extra_beats: TeachingBeat) -> ConceptTeachingPlan:
    base: list[TeachingBeat] = [
        TeachingBeat(
            beat_type="hook",
            speech_guidance="Why does the ladder slip?",
            target_duration_seconds=15,
        ),
        TeachingBeat(
            beat_type="big_picture",
            speech_guidance="Triangles measure the world.",
            target_duration_seconds=25,
        ),
        TeachingBeat(
            beat_type="first_principles",
            speech_guidance="Squares on sides.",
            target_duration_seconds=40,
        ),
    ]
    return ConceptTeachingPlan(
        concept_title="Pythagoras",
        concept_index=concept_index,
        opening_hook="Ladder",
        core_analogy="Squares",
        prerequisite_bridge="Right angles",
        beats=base + list(extra_beats),
        board_pattern="concept_intro",
        visual_narrative="Right triangle plus squares on the sides.",
    )


def _chapter_with_plan(plan: ConceptTeachingPlan, topic_id: str = "t1") -> Chapter:
    ch = Chapter(
        chapter_id="ch1",
        chapter_index=1,
        title="Chapter 1",
        summary="",
        page_start=1,
        page_end=10,
        topic_ids=[topic_id],
    )
    ch.lecture_plan = ChapterLecturePlan(
        chapter_id="ch1",
        chapter_title="Chapter 1",
        chapter_arc="A short story about right triangles.",
        opening_hook="The slipping ladder",
        concept_sequence=[topic_id],
        coverage_checklist=[],
        length_budget_seconds=240,
        per_concept_budget_seconds={topic_id: 240},
        closing_summary="",
    )
    ch.concept_plans = [plan]
    return ch


def _diagram(beat_id: str, *, with_roles: bool = True) -> Diagram:
    dictionary = {}
    if with_roles:
        dictionary = {
            "el1": {"role": "hypotenuse"},
            "el2": {"role": "opposite_side"},
        }
    return Diagram(
        diagram_id="d1",
        renderer=DiagramRenderer.SVG,
        render_data={
            "width": 800,
            "height": 600,
            "elements": [],
            "dictionary": dictionary,
        },
        description="Right triangle",
        linked_topic_ids=["t1"],
        linked_beat_id=beat_id,
    )


# ---------------------------------------------------------------------------
# Helper-unit tests
# ---------------------------------------------------------------------------


def test_estimator_strips_markers() -> None:
    # 3 words, 2.5 wps → 1.2s
    assert round(_estimate_seconds("a b c <<X>>", 2.5), 2) == 1.2


def test_audio_targets_extracts_ids() -> None:
    text = "<<WRITE_EQUATION:F=ma|id=eq-1>> then <<WRITE_KEY:Newton|id=key-9>>"
    assert _extract_audio_targets(text) == ["eq-1", "key-9"]


def test_markdown_fence_stripped() -> None:
    assert _strip_markdown_fence("```\nHello there\n```") == "Hello there"
    assert _strip_markdown_fence("plain") == "plain"


# ---------------------------------------------------------------------------
# write_for_chapter behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_emits_narration_per_beat() -> None:
    plan = _arc_plan(0)
    chapter = _chapter_with_plan(plan)
    llm = _StubProvider(
        canned_texts=[
            "Hello, I am a hook narration. Quite short.",
            "Hello, this is big picture. Slightly longer than the hook.",
            "Here we go from first principles, building the intuition gently from the ground up.",
        ]
    )
    writer = BeatNarrationWriter(llm, config=BeatNarrationConfig(concurrency=1))

    narrations, report = await writer.write_for_chapter(
        chapter=chapter,
        topics_by_id={"t1": _topic()},
        diagrams_by_beat_id={},
    )

    assert len(narrations) == 3
    assert {n.beat_type for n in narrations} == {
        "hook",
        "big_picture",
        "first_principles",
    }
    assert all(n.beat_id.startswith("t1_b") for n in narrations)
    assert report.beats_seen == 3
    assert report.beats_written == 3


@pytest.mark.asyncio
async def test_active_diagram_roles_appear_in_user_prompt() -> None:
    # Hook + big_picture + first_principles, then a visual_build beat that
    # introduces a design diagram.
    visual_build = TeachingBeat(
        beat_type="visual_build",
        speech_guidance="Show the triangle.",
        visual=VisualBeatAction(
            tool="draw_design_diagram",
            description="Right triangle with sides labelled.",
            zone="center-center",
        ),
        target_duration_seconds=20,
    )
    plan = _arc_plan(0, visual_build)
    chapter = _chapter_with_plan(plan)
    diagrams_by_beat_id = {"t1_b3": _diagram("t1_b3", with_roles=True)}
    llm = _StubProvider(canned_texts=["X. " * 30])  # any non-empty text per beat
    writer = BeatNarrationWriter(llm, config=BeatNarrationConfig(concurrency=1))

    await writer.write_for_chapter(
        chapter=chapter,
        topics_by_id={"t1": _topic()},
        diagrams_by_beat_id=diagrams_by_beat_id,
    )

    # Find the prompt for the visual_build beat (the 4th in the captured list).
    user_prompts = [u for _s, u in llm.captured_prompts]
    visual_build_prompt = next(p for p in user_prompts if "visual_build" in p)
    assert "hypotenuse" in visual_build_prompt
    assert "opposite_side" in visual_build_prompt
    assert "diagram_id: `d1`" in visual_build_prompt


@pytest.mark.asyncio
async def test_no_active_diagram_no_role_section() -> None:
    """Hook (first beat, no diagram) sees the 'No active diagram' notice."""
    plan = _arc_plan(0)
    chapter = _chapter_with_plan(plan)
    llm = _StubProvider(canned_texts=["narration"])
    writer = BeatNarrationWriter(llm, config=BeatNarrationConfig(concurrency=1))

    await writer.write_for_chapter(
        chapter=chapter,
        topics_by_id={"t1": _topic()},
        diagrams_by_beat_id={},
    )

    hook_prompt = next(u for _s, u in llm.captured_prompts if "**hook**" in u)
    assert "No active diagram" in hook_prompt or "Active diagram\nNone" in hook_prompt
    assert "Emit NO FOCUS" in hook_prompt


@pytest.mark.asyncio
async def test_prior_beat_carry_forward_diagram() -> None:
    """A later beat with no own diagram inherits the prior beat's diagram."""
    early_draw = TeachingBeat(
        beat_type="visual_build",
        speech_guidance="Draw the triangle.",
        visual=VisualBeatAction(
            tool="draw_design_diagram",
            description="Right triangle.",
        ),
        target_duration_seconds=20,
    )
    later_explain = TeachingBeat(
        beat_type="explain",
        speech_guidance="Now talk about it.",
        target_duration_seconds=20,
    )
    plan = _arc_plan(0, early_draw, later_explain)
    chapter = _chapter_with_plan(plan)
    diagrams_by_beat_id = {"t1_b3": _diagram("t1_b3", with_roles=True)}
    llm = _StubProvider(canned_texts=["txt"])
    writer = BeatNarrationWriter(llm, config=BeatNarrationConfig(concurrency=1))

    await writer.write_for_chapter(
        chapter=chapter,
        topics_by_id={"t1": _topic()},
        diagrams_by_beat_id=diagrams_by_beat_id,
    )

    explain_prompt = next(u for _s, u in llm.captured_prompts if "**explain**" in u)
    assert "hypotenuse" in explain_prompt  # carried forward


@pytest.mark.asyncio
async def test_target_words_derived_from_target_seconds() -> None:
    plan = _arc_plan(0)
    chapter = _chapter_with_plan(plan)
    llm = _StubProvider(canned_texts=["narration"])
    writer = BeatNarrationWriter(
        llm,
        config=BeatNarrationConfig(concurrency=1, target_wps=2.5),
    )
    await writer.write_for_chapter(
        chapter=chapter,
        topics_by_id={"t1": _topic()},
        diagrams_by_beat_id={},
    )
    # hook target_duration_seconds=15 → target_words=int(15*2.5)=37
    hook_prompt = next(u for _s, u in llm.captured_prompts if "**hook**" in u)
    assert "~37 words" in hook_prompt
    # first_principles target_duration_seconds=40 → 100 words
    fp_prompt = next(u for _s, u in llm.captured_prompts if "**first_principles**" in u)
    assert "~100 words" in fp_prompt


@pytest.mark.asyncio
async def test_failed_llm_returns_empty_text_needs_review() -> None:
    plan = _arc_plan(0)
    chapter = _chapter_with_plan(plan)
    llm = _StubProvider(canned_texts=[], raise_on_call=True)
    writer = BeatNarrationWriter(llm, config=BeatNarrationConfig(concurrency=1))

    narrations, report = await writer.write_for_chapter(
        chapter=chapter,
        topics_by_id={"t1": _topic()},
        diagrams_by_beat_id={},
    )
    assert len(narrations) == 3
    assert all(n.text == "" for n in narrations)
    assert all(n.needs_review for n in narrations)
    assert report.beats_written == 0


@pytest.mark.asyncio
async def test_empty_response_marks_needs_review() -> None:
    plan = _arc_plan(0)
    chapter = _chapter_with_plan(plan)
    llm = _StubProvider(canned_texts=["", "valid", "valid"])
    writer = BeatNarrationWriter(llm, config=BeatNarrationConfig(concurrency=1))

    narrations, _report = await writer.write_for_chapter(
        chapter=chapter,
        topics_by_id={"t1": _topic()},
        diagrams_by_beat_id={},
    )
    # The first to actually return "" will be one of the three (order may
    # vary under concurrency=1, but we expect at least one empty + needs_review).
    empty_beats = [n for n in narrations if not n.text]
    assert empty_beats, "expected at least one empty-text BeatNarration"
    assert all(n.needs_review for n in empty_beats)


@pytest.mark.asyncio
async def test_word_count_off_target_flags_needs_review() -> None:
    # target_words for hook (15s * 2.5wps) = 37. We return 3 words → flag.
    plan = _arc_plan(0)
    chapter = _chapter_with_plan(plan)
    llm = _StubProvider(canned_texts=["one two three"])  # 3 words << 37*0.5
    writer = BeatNarrationWriter(llm, config=BeatNarrationConfig(concurrency=1))

    narrations, _report = await writer.write_for_chapter(
        chapter=chapter,
        topics_by_id={"t1": _topic()},
        diagrams_by_beat_id={},
    )
    hook = next(n for n in narrations if n.beat_type == "hook")
    assert hook.needs_review is True
    assert hook.text == "one two three"  # text preserved


@pytest.mark.asyncio
async def test_rewrite_uses_new_target_seconds() -> None:
    plan = _arc_plan(0)
    chapter = _chapter_with_plan(plan)
    llm = _StubProvider(canned_texts=["initial", "shorter"])
    writer = BeatNarrationWriter(llm, config=BeatNarrationConfig(concurrency=1))

    narrations, _report = await writer.write_for_chapter(
        chapter=chapter,
        topics_by_id={"t1": _topic()},
        diagrams_by_beat_id={},
    )
    explain = narrations[0]  # any beat
    new = await writer.rewrite(
        explain,
        new_target_seconds=10,
        topic=_topic(),
        plan=plan,
        beat=plan.beats[explain.beat_index],
    )
    assert new.target_duration_seconds == 10
    # The most-recent prompt had "Target duration: 10s".
    _last_sys, last_user = llm.captured_prompts[-1]
    assert "Target duration: 10s" in last_user


@pytest.mark.asyncio
async def test_audio_targets_populated_from_emitted_markers() -> None:
    plan = _arc_plan(0)
    chapter = _chapter_with_plan(plan)
    llm = _StubProvider(
        canned_texts=[
            "I write the law. <<WRITE_EQUATION:F=ma|id=eq-7>> Done.",
            "x",
            "x",
        ]
    )
    writer = BeatNarrationWriter(llm, config=BeatNarrationConfig(concurrency=1))
    narrations, _report = await writer.write_for_chapter(
        chapter=chapter,
        topics_by_id={"t1": _topic()},
        diagrams_by_beat_id={},
    )
    with_marker = [n for n in narrations if n.audio_targets]
    assert with_marker, "expected at least one narration to carry audio_targets"
    assert "eq-7" in with_marker[0].audio_targets
