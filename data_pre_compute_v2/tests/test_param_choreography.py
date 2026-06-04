"""Workstream A5 — narration-driven parameter choreography (Phase III).

The choreography can jump (`set_param`) or sweep (`animate_param`) a diagram
parameter while the teacher talks — the sweep IS the explanation. These tests
cover the whole chain: ChoreographyStep authoring + validators, narrator marker
emission, chunker parse, walker validation (against template / LLM params, plus
the template-focus fix the param work depends on), audio-pipeline event render,
and the D3 `from`-alias serialization the manifest persist path relies on.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from lecture_pipeline_v2.curriculum.lecture_plan.lesson_narrator import (
    LessonNarrationReport,
    _emit_action_markers,
)
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_plan_models import (
    ChoreographyAction,
    ChoreographyStep,
)
from lecture_pipeline_v2.curriculum.manifest_composer import ManifestComposer
from lecture_pipeline_v2.curriculum.media.audio_pipeline import (
    AudioPipeline,
    AudioPipelineReport,
)
from lecture_pipeline_v2.curriculum.models import (
    AnimateParameterEvent,
    Manifest,
    SetParameterEvent,
)
from lecture_pipeline_v2.tts.chunker import (
    AnimateParamFragment,
    SetParamFragment,
    split_script,
)


def _tmpl(mode: str) -> SimpleNamespace:
    """A canonical-template diagram as the generator builds it: empty
    render_data + template_concept_id. Its element vocab + params come from the
    catalog."""
    return SimpleNamespace(
        render_data={},
        template_concept_id="right-triangle-trig",
        presentation_mode=mode,
    )


# --- chunker ------------------------------------------------------------------


def test_chunker_parses_set_param() -> None:
    frag = split_script("<<SET_PARAM:theta|value=20>>")[0]
    assert isinstance(frag, SetParamFragment)
    assert frag.name == "theta" and frag.value == 20.0


def test_chunker_parses_animate_param() -> None:
    full = split_script("<<ANIMATE_PARAM:theta|to=55|from=20|duration=2000>>")[0]
    assert isinstance(full, AnimateParamFragment)
    assert full.name == "theta" and full.to == 55.0
    assert full.from_value == 20.0 and full.duration_ms == 2000
    # from / duration are optional → None when absent
    minimal = split_script("<<ANIMATE_PARAM:theta|to=55>>")[0]
    assert minimal.from_value is None and minimal.duration_ms is None


# --- events + D3 from-alias ---------------------------------------------------


def test_set_parameter_event_shape() -> None:
    ev = SetParameterEvent(diagram_id="A", name="theta", value=20)
    assert ev.type == "set_parameter" and ev.value == 20.0


def test_animate_parameter_event_from_alias_serialization() -> None:
    """D3: `from_` must serialize as the JSON key `from` under by_alias (the
    cypher persist path uses by_alias=True). Without it the frontend reads
    `ev.from === undefined` and the tween starts from the wrong value."""
    ev = AnimateParameterEvent(diagram_id="A", name="theta", to=55, from_=20)
    default_keys = json.loads(ev.model_dump_json())
    alias_keys = json.loads(ev.model_dump_json(by_alias=True))
    assert "from_" in default_keys and "from" not in default_keys
    assert "from" in alias_keys and alias_keys["from"] == 20
    assert "from_" not in alias_keys


def test_manifest_union_validates_and_dumps_param_events() -> None:
    m = Manifest(
        events=[
            {"type": "set_parameter", "diagram_id": "A", "name": "theta", "value": 20},
            {
                "type": "animate_parameter",
                "diagram_id": "A",
                "name": "theta",
                "to": 55,
                "from": 20,
                "duration_ms": 2000,
            },
        ]
    )
    assert isinstance(m.events[0], SetParameterEvent)
    assert isinstance(m.events[1], AnimateParameterEvent)
    assert m.events[1].from_ == 20  # validated via the 'from' alias
    # whole-manifest by_alias dump (what cypher_generator does) emits 'from'
    dumped = json.loads(m.model_dump_json(by_alias=True))
    assert dumped["events"][1]["from"] == 20


# --- ChoreographyStep validators ----------------------------------------------


def test_choreography_step_set_param_requires_fields() -> None:
    with pytest.raises(ValueError, match="set_param requires param_value"):
        ChoreographyStep(
            narration="set it",
            actions=[ChoreographyAction.set_param],
            param_name="theta",
        )
    with pytest.raises(ValueError, match="requires param_name"):
        ChoreographyStep(
            narration="set it", actions=[ChoreographyAction.set_param], param_value=20
        )


def test_choreography_step_animate_param_requires_fields() -> None:
    with pytest.raises(ValueError, match="animate_param requires param_to"):
        ChoreographyStep(
            narration="sweep it",
            actions=[ChoreographyAction.animate_param],
            param_name="theta",
        )
    # well-formed passes
    step = ChoreographyStep(
        narration="sweep it",
        actions=[ChoreographyAction.animate_param],
        param_name="theta",
        param_to=55,
    )
    assert step.param_to == 55


def test_choreography_step_rejects_both_param_actions() -> None:
    with pytest.raises(ValueError, match="set_param OR animate_param, not"):
        ChoreographyStep(
            narration="x",
            actions=[ChoreographyAction.set_param, ChoreographyAction.animate_param],
            param_name="theta",
            param_value=20,
            param_to=55,
        )


# --- narrator marker emission -------------------------------------------------


def test_narrator_emits_set_param_marker_before() -> None:
    step = ChoreographyStep(
        narration="Start at twenty degrees.",
        actions=[ChoreographyAction.set_param],
        param_name="theta",
        param_value=20,
    )
    before, after = _emit_action_markers(step, 0, LessonNarrationReport())
    assert any("<<SET_PARAM:theta|value=20" in m for m in before)
    assert after == []  # param actions are BEFORE — the change runs during speech


def test_narrator_emits_animate_param_marker_before() -> None:
    step = ChoreographyStep(
        narration="Watch the side grow.",
        actions=[ChoreographyAction.animate_param],
        param_name="theta",
        param_to=55,
        param_from=20,
        param_duration_ms=2000,
    )
    before, _ = _emit_action_markers(step, 0, LessonNarrationReport())
    marker = next(m for m in before if m.startswith("<<ANIMATE_PARAM"))
    assert "theta" in marker and "to=55" in marker
    assert "from=20" in marker and "duration=2000" in marker


# --- walker validation (incl. the template-focus fix the params depend on) ----


def test_walker_template_focus_resolves() -> None:
    """Regression guard: a template diagram (empty render_data) must resolve
    focus against the catalog element ids, not drop with role_unknown."""
    composer = ManifestComposer(diagrams_by_id={"A": _tmpl("build_up")})
    out = asyncio.run(
        composer.compose(split_script("<<SHOW_DIAGRAM:A>> hyp <<FOCUS:hypotenuse>>"))
    )
    focus = [f for f in out if getattr(f, "kind", None) == "focus"]
    assert len(focus) == 1
    assert focus[0].element_id == "hypotenuse" and focus[0].diagram_id == "A"
    assert composer.last_report.drops_by_reason == {}


def test_walker_animate_param_on_template_resolves() -> None:
    composer = ManifestComposer(diagrams_by_id={"A": _tmpl("overview")})
    out = asyncio.run(
        composer.compose(
            split_script(
                "<<SHOW_DIAGRAM:A>> watch <<ANIMATE_PARAM:theta|to=55|from=20>>"
            )
        )
    )
    anim = [f for f in out if getattr(f, "kind", None) == "animate_parameter"]
    assert len(anim) == 1
    assert anim[0].name == "theta" and anim[0].diagram_id == "A"
    assert anim[0].to == 55.0 and anim[0].from_value == 20.0


def test_walker_unknown_param_drops() -> None:
    composer = ManifestComposer(diagrams_by_id={"A": _tmpl("overview")})
    out = asyncio.run(
        composer.compose(
            split_script("<<SHOW_DIAGRAM:A>> x <<SET_PARAM:bogus|value=5>>")
        )
    )
    assert [f for f in out if getattr(f, "kind", None) == "set_parameter"] == []
    assert composer.last_report.drops_by_reason.get("param_unknown") == 1


def test_walker_param_without_active_diagram_drops() -> None:
    composer = ManifestComposer(diagrams_by_id={})
    out = asyncio.run(composer.compose(split_script("<<SET_PARAM:theta|value=5>>")))
    assert [f for f in out if getattr(f, "kind", None) == "set_parameter"] == []
    assert composer.last_report.drops_by_reason.get("no_active_diagram") == 1


def test_walker_llm_diagram_declared_param_resolves() -> None:
    llm = SimpleNamespace(
        render_data={
            "dictionary": {"el": {"role": "r"}},
            "parameters": [{"name": "k", "min": 0, "max": 1, "default": 0.5}],
        },
        presentation_mode="overview",
    )
    composer = ManifestComposer(diagrams_by_id={"B": llm})
    out = asyncio.run(
        composer.compose(split_script("<<SHOW_DIAGRAM:B>> x <<SET_PARAM:k|value=0.8>>"))
    )
    sp = [f for f in out if getattr(f, "kind", None) == "set_parameter"]
    assert len(sp) == 1 and sp[0].name == "k" and sp[0].value == 0.8


# --- audio_pipeline render ----------------------------------------------------


def test_audio_pipeline_renders_param_events() -> None:
    ap = AudioPipeline.__new__(AudioPipeline)  # branch reads no state
    events = asyncio.run(
        ap._render_fragments(
            fragments=[
                SetParamFragment(
                    kind="set_parameter", name="theta", value=20, diagram_id="A"
                ),
                AnimateParamFragment(
                    kind="animate_parameter",
                    name="theta",
                    to=55,
                    from_value=20,
                    duration_ms=2000,
                    diagram_id="A",
                ),
            ],
            chapter_dir=Path("."),
            topic_id="t",
            role="chapter",
            report=AudioPipelineReport(),
        )
    )
    assert isinstance(events[0], SetParameterEvent) and events[0].value == 20.0
    assert isinstance(events[1], AnimateParameterEvent)
    assert (
        events[1].from_ == 20.0
        and events[1].to == 55.0
        and events[1].duration_ms == 2000
    )
