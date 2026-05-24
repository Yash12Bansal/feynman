"""Back-compat integration test for the doc-18 spotlight transition.

The Phase 2 era fixture (`fixtures/phase2_annotated_script.txt`) uses the
legacy PIN/CALLOUT/BRACKET/HIGHLIGHT/PULSE markers. After the spotlight
redesign:
  - Chunker must still parse those markers (so old narration strings load).
  - Walker must drop the resulting fragments silently (legacy deprecated).
  - Composer must emit ZERO annotation events for them.

This file replaces the original "composer emits a sensible PIN/CALLOUT
distribution" tests. It exists for one re-ingest cycle while in-flight
extraction files transition to FOCUS-only narration. Delete after that.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from lecture_pipeline_v2.curriculum.manifest_composer import ManifestComposer
from lecture_pipeline_v2.tts.chunker import (
    BracketFragment,
    ClearAnnotationsFragment,
    DiagramFragment,
    FocusFragment,
    HighlightFragment,
    PinFragment,
    PulseFragment,
    TextFragment,
    split_script,
)


TRIANGLE_DICTIONARY = {
    "el_hyp": {
        "role": "hypotenuse",
        "semantic": "the slanted side opposite the right angle",
        "position": "top-right diagonal",
        "bounds": [200, 200, 200, 5],
    },
    "el_opp": {
        "role": "opposite_side",
        "semantic": "the vertical leg",
        "position": "right",
        "bounds": [400, 200, 5, 200],
    },
    "el_adj": {
        "role": "adjacent_side",
        "semantic": "the horizontal leg",
        "position": "bottom",
        "bounds": [200, 400, 200, 5],
    },
    "el_theta": {
        "role": "theta_angle",
        "semantic": "the angle at the corner",
        "position": "bottom-left",
        "bounds": [220, 380, 40, 20],
    },
}


def _load_legacy_fixture() -> str:
    fixture = Path(__file__).parent / "fixtures" / "phase2_annotated_script.txt"
    return fixture.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_legacy_fixture_chunker_still_parses_markers():
    """Back-compat: chunker still recognizes all 5 legacy annotation markers."""
    script = _load_legacy_fixture()
    frags = split_script(script)

    assert any(isinstance(f, DiagramFragment) for f in frags)
    assert any(isinstance(f, PinFragment) for f in frags)
    assert any(isinstance(f, BracketFragment) for f in frags)
    assert any(isinstance(f, HighlightFragment) for f in frags)
    assert any(isinstance(f, PulseFragment) for f in frags)
    assert any(isinstance(f, ClearAnnotationsFragment) for f in frags)
    assert any(isinstance(f, TextFragment) for f in frags)


@pytest.mark.asyncio
async def test_legacy_fixture_composer_drops_all_legacy_annotations():
    """After spotlight redesign: walker drops legacy fragments silently."""
    script = _load_legacy_fixture()
    frags = split_script(script)

    diagram = SimpleNamespace(
        diagram_id="d_triangle",
        render_data={"dictionary": TRIANGLE_DICTIONARY},
    )
    composer = ManifestComposer(diagrams_by_id={"d_triangle": diagram})
    out = await composer.compose(frags)

    # No legacy annotation fragments survive the walker.
    assert not any(isinstance(f, PinFragment) for f in out)
    assert not any(isinstance(f, BracketFragment) for f in out)
    assert not any(isinstance(f, HighlightFragment) for f in out)
    assert not any(isinstance(f, PulseFragment) for f in out)
    # CLEAR_ANNOTATIONS still emits (it's the alias for RESET_FOCUS).
    assert any(isinstance(f, ClearAnnotationsFragment) for f in out)

    # Drops counted under legacy_annotation_deprecated.
    assert (
        composer.last_report.drops_by_reason.get("legacy_annotation_deprecated", 0) >= 1
    )


@pytest.mark.asyncio
async def test_focus_fixture_round_trip():
    """A focus-style narration round-trips through chunker + composer cleanly."""
    script = (
        "<<SHOW_DIAGRAM:d_triangle>> "
        "Look at this triangle. <<FOCUS:hypotenuse|text=hypotenuse>> "
        "The slanted side is the hypotenuse. "
        "<<FOCUS:opposite_side|text=opposite>> "
        "This vertical leg is the opposite side. "
        "<<RESET_FOCUS>>"
    )
    frags = split_script(script)

    diagram = SimpleNamespace(
        diagram_id="d_triangle",
        render_data={"dictionary": TRIANGLE_DICTIONARY},
    )
    composer = ManifestComposer(diagrams_by_id={"d_triangle": diagram})
    out = await composer.compose(frags)

    focuses = [f for f in out if isinstance(f, FocusFragment)]
    assert len(focuses) == 2
    assert focuses[0].role == "hypotenuse"
    assert focuses[0].text == "hypotenuse"
    assert focuses[1].role == "opposite_side"
    assert all(f.diagram_id == "d_triangle" for f in focuses)
    # RESET_FOCUS emits as ClearAnnotationsFragment.
    clears = [f for f in out if isinstance(f, ClearAnnotationsFragment)]
    assert len(clears) == 1
