"""DiagramSpecGenerator (Phase 4c) — per-beat generation smoke tests."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from feynman_teaching_kernel import ConceptTeachingPlan, TeachingBeat, VisualBeatAction

from lecture_pipeline_v2.curriculum.enrichment.diagram_spec_generator import (
    DESIGN_DIAGRAM_TOOLS,
    DiagramSpecGenerator,
)
from lecture_pipeline_v2.curriculum.models import Topic
from lecture_pipeline_v2.llm.base import LLMProvider, LLMResponse


@dataclass
class _StubProvider(LLMProvider):
    """LLM stub — bypasses LLMProvider's abstract __init__."""

    canned_specs: list[str]
    captured_prompts: list[tuple[str, str]]

    def __init__(self, canned_specs: list[str]) -> None:
        self.canned_specs = list(canned_specs)
        self.captured_prompts = []

    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        return self.generate_json(system_prompt, user_prompt)

    def generate_json(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        self.captured_prompts.append((system_prompt, user_prompt))
        # Pop in order; reuse last spec if we run out.
        if len(self.canned_specs) > 1:
            content = self.canned_specs.pop(0)
        else:
            content = self.canned_specs[0] if self.canned_specs else "{}"
        return LLMResponse(content=content, model="stub")


def _spec_json(title: str, n_elements: int = 3) -> str:
    return json.dumps(
        {
            "title": title,
            "width": 900,
            "height": 650,
            "backgroundColor": "transparent",
            "elements": [
                {
                    "type": "svg_line",
                    "id": f"el{i}",
                    "x1": 0,
                    "y1": 0,
                    "x2": 10,
                    "y2": 10,
                }
                for i in range(n_elements)
            ],
            "dictionary": {},
        }
    )


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
    """Build a ConceptTeachingPlan with the mandatory hook/big_picture/first_principles arc."""
    base_beats: list[TeachingBeat] = [
        TeachingBeat(beat_type="hook", speech_guidance="Why does the ladder slip?"),
        TeachingBeat(
            beat_type="big_picture", speech_guidance="Triangles measure the world."
        ),
        TeachingBeat(beat_type="first_principles", speech_guidance="Squares on sides."),
    ]
    return ConceptTeachingPlan(
        concept_title="Pythagoras",
        concept_index=concept_index,
        opening_hook="Ladder",
        core_analogy="Squares",
        prerequisite_bridge="Right angles",
        beats=base_beats + list(extra_beats),
        board_pattern="concept_intro",
        visual_narrative="A right triangle appears, then squares on each side.",
    )


@pytest.mark.asyncio
async def test_happy_path_emits_one_diagram_per_design_beat() -> None:
    """Per-beat generator emits exactly one Diagram per design-diagram beat."""
    explain = TeachingBeat(
        beat_type="explain",
        speech_guidance="a^2 + b^2 = c^2.",
        visual=VisualBeatAction(
            tool="draw_design_diagram",
            description="Right triangle with sides a, b, c labelled.",
            zone="center-center",
        ),
    )
    plan = _arc_plan(0, explain)
    llm = _StubProvider(canned_specs=[_spec_json("right-triangle")])
    gen = DiagramSpecGenerator(llm, concurrency=2)

    diagrams, report = await gen.generate_for_chapter(
        topics_by_id={"t1": _topic()},
        concept_plans=[plan],
        topic_id_by_plan_index={0: "t1"},
    )

    assert report.beats_design_diagram == 1
    assert report.diagrams_generated == 1
    assert len(diagrams) == 1
    assert (
        diagrams[0].linked_beat_id == "t1_b3"
    )  # explain is at index 3 (after the 3 arc beats)
    assert diagrams[0].linked_topic_ids == ["t1"]
    assert diagrams[0].description == "Right triangle with sides a, b, c labelled."
    # System prompt is the verbatim design_agent prompt.
    sys_prompt, user_prompt = llm.captured_prompts[0]
    assert "expert teacher" in sys_prompt
    assert "right triangle" in user_prompt.lower()
    assert "## Brief" in user_prompt
    assert "## Context" in user_prompt


@pytest.mark.asyncio
async def test_skips_non_design_tools() -> None:
    """Beats with write_equation/draw_scene/etc. do not produce diagrams."""
    write_eq = TeachingBeat(
        beat_type="explain",
        speech_guidance="State the formula.",
        visual=VisualBeatAction(tool="write_equation", description="a^2 + b^2 = c^2"),
    )
    draw_scene = TeachingBeat(
        beat_type="example",
        speech_guidance="Show a ladder.",
        visual=VisualBeatAction(
            tool="draw_scene", description="A ladder leaning on a wall."
        ),
    )
    plan = _arc_plan(0, write_eq, draw_scene)
    llm = _StubProvider(canned_specs=[])  # LLM should never be called

    gen = DiagramSpecGenerator(llm, concurrency=2)
    diagrams, report = await gen.generate_for_chapter(
        topics_by_id={"t1": _topic()},
        concept_plans=[plan],
        topic_id_by_plan_index={0: "t1"},
    )

    assert report.beats_seen == 5  # 3 arc + 2 extra
    assert report.beats_design_diagram == 0
    assert diagrams == []
    assert llm.captured_prompts == []


@pytest.mark.asyncio
async def test_skips_beats_without_visual() -> None:
    """beat.visual is None → skipped without an LLM call."""
    speech_only = TeachingBeat(beat_type="ask", speech_guidance="What if a=3, b=4?")
    plan = _arc_plan(0, speech_only)
    llm = _StubProvider(canned_specs=[])

    gen = DiagramSpecGenerator(llm, concurrency=2)
    diagrams, report = await gen.generate_for_chapter(
        topics_by_id={"t1": _topic()},
        concept_plans=[plan],
        topic_id_by_plan_index={0: "t1"},
    )

    assert report.beats_design_diagram == 0
    assert diagrams == []


def test_python_mode_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError, match="canvas_dsl"):
        DiagramSpecGenerator(None, mode="python")


def test_unknown_mode_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown.*mode"):
        DiagramSpecGenerator(None, mode="magic")


def test_auto_mode_aliases_to_direct() -> None:
    g = DiagramSpecGenerator(None, mode="auto")
    assert g.mode == "direct"


@pytest.mark.asyncio
async def test_prior_design_beats_appear_in_context() -> None:
    """Later design-diagram beats see prior design-diagram beats' descriptions in their context."""
    first_diagram = TeachingBeat(
        beat_type="visual_build",
        speech_guidance="Draw the triangle.",
        visual=VisualBeatAction(
            tool="draw_design_diagram", description="Right triangle alone."
        ),
    )
    second_diagram = TeachingBeat(
        beat_type="visual_build",
        speech_guidance="Add the squares.",
        visual=VisualBeatAction(
            tool="draw_design_diagram", description="Squares on each side."
        ),
    )
    plan = _arc_plan(0, first_diagram, second_diagram)
    # Two distinct specs returned so we can inspect both calls.
    llm = _StubProvider(
        canned_specs=[
            _spec_json("triangle"),
            _spec_json("triangle-with-squares"),
        ]
    )
    gen = DiagramSpecGenerator(llm, concurrency=1)
    diagrams, _ = await gen.generate_for_chapter(
        topics_by_id={"t1": _topic()},
        concept_plans=[plan],
        topic_id_by_plan_index={0: "t1"},
    )

    assert len(diagrams) == 2
    # Two captured prompts; the second one should mention the first's description.
    assert len(llm.captured_prompts) == 2
    # Either prompt-order may be observed (asyncio.gather doesn't preserve order),
    # so check both prompts for the cross-reference.
    seen_prior_reference = any(
        "Right triangle alone" in user
        for _sys, user in llm.captured_prompts
        if "Squares on each side" in user
    )
    assert seen_prior_reference, (
        "Later beat must see prior design-diagram beat in its context"
    )


@pytest.mark.asyncio
async def test_regenerate_for_beat_passes_hint_through() -> None:
    """regenerate_for_beat appends the CORRECTIVE HINT section to the user prompt."""
    draw = TeachingBeat(
        beat_type="visual_build",
        speech_guidance="Draw the triangle.",
        visual=VisualBeatAction(
            tool="draw_design_diagram", description="Right triangle."
        ),
    )
    plan = _arc_plan(0, draw)
    llm = _StubProvider(canned_specs=[_spec_json("triangle-retry")])
    gen = DiagramSpecGenerator(llm, concurrency=1)
    diagram = await gen.regenerate_for_beat(
        _topic(),
        plan,
        draw,
        beat_index=3,
        hint="Move the right-angle marker to vertex A.",
    )
    assert diagram is not None
    assert diagram.linked_beat_id == "t1_b3"
    _sys, user = llm.captured_prompts[0]
    assert "CORRECTIVE HINT" in user
    assert "vertex A" in user


@pytest.mark.asyncio
async def test_unknown_design_tools_filter_is_design_only() -> None:
    """The DESIGN_DIAGRAM_TOOLS set is the authoritative filter for what produces a diagram."""
    assert DESIGN_DIAGRAM_TOOLS == frozenset(
        {"draw_design_diagram", "modify_design_diagram"}
    )
