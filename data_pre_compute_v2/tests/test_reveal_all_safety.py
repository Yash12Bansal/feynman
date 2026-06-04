"""Workstream B — build_up reveal-all safety (Phase II).

A build_up diagram starts blank and reveals its elements on focus; if the
choreography never focuses an element it would stay hidden forever. These tests
assert the two safety nets:

  - the walker injects a reveal-all (`RevealStepFragment(step=REVEAL_ALL_STEP)`)
    for the OUTGOING build_up diagram when a different diagram is shown, and
  - it exposes the still-open build_up id so the audio pipeline can append a
    chapter-end reveal-all.

The frontend clamps step=REVEAL_ALL_STEP to the last reveal group and fills
every group idempotently, so the sentinel reveals everything and a lecture
never ends (or swaps away) on a half-built figure.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from lecture_pipeline_v2.curriculum.manifest_composer import ManifestComposer
from lecture_pipeline_v2.curriculum.media.audio_pipeline import (
    AudioPipeline,
    AudioPipelineReport,
)
from lecture_pipeline_v2.curriculum.models import Manifest, RevealStepEvent
from lecture_pipeline_v2.tts.chunker import (
    REVEAL_ALL_STEP,
    DiagramFragment,
    RevealStepFragment,
    split_script,
)


def _diagram(mode: str | None) -> SimpleNamespace:
    """Minimal diagram — the walker only reads render_data['dictionary'] and
    presentation_mode."""
    return SimpleNamespace(
        render_data={"dictionary": {"el1": {"role": "r1"}, "el2": {"role": "r2"}}},
        presentation_mode=mode,
    )


def _show(diagram_id: str) -> DiagramFragment:
    return DiagramFragment(kind="show_diagram", diagram_id=diagram_id)


# --- chunker ------------------------------------------------------------------


def test_chunker_parses_reveal_step_marker() -> None:
    assert split_script("<<REVEAL_STEP:3>>")[0] == RevealStepFragment(
        kind="reveal_step", step=3
    )
    # absent index → 0; non-numeric → 0 (tolerant); negative clamps to 0
    assert split_script("<<REVEAL_STEP>>")[0].step == 0
    assert split_script("<<REVEAL_STEP:abc>>")[0].step == 0
    assert split_script("<<REVEAL_STEP:-5>>")[0].step == 0


# --- event / discriminated union ---------------------------------------------


def test_reveal_step_event_in_manifest_union() -> None:
    m = Manifest(events=[{"type": "reveal_step", "diagram_id": "d1", "step": 10000}])
    assert isinstance(m.events[0], RevealStepEvent)
    assert m.events[0].step == 10000
    with pytest.raises(ValueError):  # step is ge=0
        RevealStepEvent(diagram_id="d1", step=-1)


# --- walker injection on swap -------------------------------------------------


def test_walker_injects_reveal_all_on_build_up_swap() -> None:
    composer = ManifestComposer(
        diagrams_by_id={"A": _diagram("build_up"), "B": _diagram("overview")}
    )
    out = asyncio.run(composer.compose([_show("A"), _show("B")]))
    kinds = [f.kind for f in out]
    # reveal-all for A fires while A is still active, BEFORE B's show resets it.
    assert kinds == ["show_diagram", "reveal_step", "show_diagram"]
    assert out[1].diagram_id == "A"  # the OUTGOING build_up diagram
    assert out[1].step == REVEAL_ALL_STEP
    assert composer.open_build_up_diagram_id is None  # B is overview


def test_walker_tracks_open_build_up_for_chapter_end() -> None:
    composer = ManifestComposer(diagrams_by_id={"A": _diagram("build_up")})
    asyncio.run(composer.compose([_show("A")]))
    composer.flush()
    assert composer.open_build_up_diagram_id == "A"


def test_walker_no_reveal_on_same_build_up_reshow() -> None:
    composer = ManifestComposer(diagrams_by_id={"A": _diagram("build_up")})
    out = asyncio.run(composer.compose([_show("A"), _show("A")]))
    assert [f.kind for f in out] == ["show_diagram", "show_diagram"]


def test_walker_no_reveal_between_overview_diagrams() -> None:
    composer = ManifestComposer(
        diagrams_by_id={"A": _diagram("overview"), "B": _diagram("overview")}
    )
    out = asyncio.run(composer.compose([_show("A"), _show("B")]))
    assert [f.kind for f in out] == ["show_diagram", "show_diagram"]
    assert composer.open_build_up_diagram_id is None


def test_walker_reveals_outgoing_build_up_even_when_next_is_build_up() -> None:
    composer = ManifestComposer(
        diagrams_by_id={"A": _diagram("build_up"), "B": _diagram("build_up")}
    )
    out = asyncio.run(composer.compose([_show("A"), _show("B")]))
    assert [f.kind for f in out] == ["show_diagram", "reveal_step", "show_diagram"]
    assert out[1].diagram_id == "A"
    assert composer.open_build_up_diagram_id == "B"  # B now open for chapter end


# --- authored marker stamping -------------------------------------------------


def test_authored_reveal_step_stamped_with_active_diagram() -> None:
    composer = ManifestComposer(diagrams_by_id={"A": _diagram("build_up")})
    out = asyncio.run(
        composer.compose(split_script("<<SHOW_DIAGRAM:A>> text <<REVEAL_STEP:2>>"))
    )
    reveal = [f for f in out if f.kind == "reveal_step"]
    assert len(reveal) == 1
    assert reveal[0].diagram_id == "A"  # stamped from the active diagram
    assert reveal[0].step == 2


def test_authored_reveal_step_dropped_without_active_diagram() -> None:
    composer = ManifestComposer(diagrams_by_id={})
    out = asyncio.run(composer.compose(split_script("<<REVEAL_STEP:1>>")))
    assert [f for f in out if f.kind == "reveal_step"] == []


# --- audio_pipeline render ----------------------------------------------------


def test_audio_pipeline_renders_reveal_step_event() -> None:
    # __new__ bypasses __init__ — the RevealStepFragment branch reads no state.
    ap = AudioPipeline.__new__(AudioPipeline)
    events = asyncio.run(
        ap._render_fragments(
            fragments=[
                RevealStepFragment(
                    kind="reveal_step", step=REVEAL_ALL_STEP, diagram_id="A"
                )
            ],
            chapter_dir=Path("."),
            topic_id="t",
            role="chapter",
            report=AudioPipelineReport(),
        )
    )
    assert len(events) == 1
    assert isinstance(events[0], RevealStepEvent)
    assert events[0].diagram_id == "A"
    assert events[0].step == REVEAL_ALL_STEP
