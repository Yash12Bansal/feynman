"""Phase 3 hand-fixture integration test.

Exercises the walker + LayoutPlanner end-to-end against a fake measurement
service (no Playwright launch). Verifies:
  - Notebook fragments gain `placement` with measured=True
  - PageBreakFragments are injected at overflow / new-diagram / writer-marker
  - PageSummary list grows monotonically as pages close
  - Phase 2 annotation behavior is unaffected when layout is enabled
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from lecture_pipeline_v2.config import LayoutConfig
from lecture_pipeline_v2.curriculum.manifest_composer import ManifestComposer
from lecture_pipeline_v2.tts.chunker import (
    AnswerFragment,
    DiagramFragment,
    EquationFragment,
    KeyPointFragment,
    NewPageFragment,
    PageBreakFragment,
    FocusFragment,
    PinFragment,
    SectionFragment,
    StepFragment,
    TextEntryFragment,
    TextFragment,
)


class FakeMeasurement:
    """Deterministic measurement service for layout tests.

    All blocks return 100px height by default. Tests can override per-content
    via `stub`.
    """

    def __init__(self, default_height: float = 100.0):
        self.default_height = default_height
        self._heights: dict[tuple[str, str], float] = {}
        # Surface a fake css_hash so MeasurementService isn't constructed.
        self.css_hash = "fake-hash"

    def stub(self, block_type: str, content: str, height: float):
        self._heights[(block_type, content)] = height

    async def measure(self, block_type, content, attrs=None, width_px=None):
        h = self._heights.get((block_type, content), self.default_height)
        return {"width": float(width_px or 540), "height": h}


def _diagram(
    diagram_id: str, view_box: str = "0 0 800 600", dictionary: dict | None = None
) -> Any:
    render = {"viewBox": view_box}
    if dictionary:
        render["dictionary"] = dictionary
    return SimpleNamespace(diagram_id=diagram_id, render_data=render)


# ---------------------------------------------------------------------------
# Single-page fits, no breaks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_page_no_breaks_emits_one_summary():
    """A few blocks that all fit on one page should produce exactly one
    PageSummary at chapter close, and zero PageBreakFragments."""
    cfg = LayoutConfig()
    measurement = FakeMeasurement(default_height=50.0)
    diagrams = {"d1": _diagram("d1")}
    composer = ManifestComposer(
        diagrams_by_id=diagrams,
        layout_config=cfg,
        measurement=measurement,  # type: ignore[arg-type]
        topic_id="t1",
    )

    fragments = [
        DiagramFragment(kind="show_diagram", diagram_id="d1"),
        TextEntryFragment(kind="text_entry", id="t1", text="One short line."),
        EquationFragment(kind="equation", id="eq-1", latex="F = ma"),
        KeyPointFragment(kind="key_point", id="key-1", text="Newton's 2nd law."),
    ]
    out = await composer.compose(fragments)
    composer.flush()

    # No PageBreakFragments
    breaks = [f for f in out if isinstance(f, PageBreakFragment)]
    assert breaks == []
    # ShowDiagram has placement stamped
    show = next(f for f in out if isinstance(f, DiagramFragment))
    assert show.placement is not None
    assert show.placement.measured is True
    # Notebook blocks all have placement
    for f in out:
        if isinstance(f, (TextEntryFragment, EquationFragment, KeyPointFragment)):
            assert f.placement is not None
            assert f.placement.measured is True
            assert f.placement.page_index == 0
    # One PageSummary closed at chapter end
    pages = composer.last_report.pages
    assert len(pages) == 1
    assert pages[0].page_index == 0
    assert pages[0].notebook_block_count == 3
    assert pages[0].slide_diagram_id == "d1"


# ---------------------------------------------------------------------------
# Text overflow triggers a page break
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_text_overflow_triggers_page_break():
    """Place enough tall blocks that one overflows → should inject a
    PageBreakFragment with reason=text_overflow."""
    cfg = LayoutConfig()
    # Notebook inner height = 800 - 60 = 740. With safety margin 8, usable
    # ~732. Each block = 200 + spacing(12) = 212. Three fit (3*212=636);
    # fourth overflows (4*212=848 > 732).
    measurement = FakeMeasurement(default_height=200.0)
    composer = ManifestComposer(
        diagrams_by_id={},
        layout_config=cfg,
        measurement=measurement,  # type: ignore[arg-type]
    )

    fragments = [
        TextEntryFragment(kind="text_entry", id=f"t{i}", text=f"block {i}")
        for i in range(5)
    ]
    out = await composer.compose(fragments)
    composer.flush()

    breaks = [f for f in out if isinstance(f, PageBreakFragment)]
    assert len(breaks) >= 1
    assert any(b.reason == "text_overflow" for b in breaks)
    # First break should sit BEFORE the overflow-triggering fragment.
    first_break_idx = next(
        i for i, f in enumerate(out) if isinstance(f, PageBreakFragment)
    )
    assert first_break_idx > 0
    # After the break, page_index advances on subsequent placements.
    after_break = [
        f for f in out[first_break_idx + 1 :] if isinstance(f, TextEntryFragment)
    ]
    assert all(f.placement.page_index >= 1 for f in after_break)


# ---------------------------------------------------------------------------
# New diagram on the same page → break with slide_action=swap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_diagram_triggers_swap_break():
    cfg = LayoutConfig()
    measurement = FakeMeasurement(default_height=50.0)
    composer = ManifestComposer(
        diagrams_by_id={"d1": _diagram("d1"), "d2": _diagram("d2")},
        layout_config=cfg,
        measurement=measurement,  # type: ignore[arg-type]
    )

    fragments = [
        DiagramFragment(kind="show_diagram", diagram_id="d1"),
        TextEntryFragment(kind="text_entry", id="t1", text="hello"),
        DiagramFragment(kind="show_diagram", diagram_id="d2"),
        TextEntryFragment(kind="text_entry", id="t2", text="world"),
    ]
    out = await composer.compose(fragments)
    composer.flush()

    breaks = [f for f in out if isinstance(f, PageBreakFragment)]
    assert len(breaks) == 1
    assert breaks[0].reason == "new_diagram"
    assert breaks[0].slide_action == "swap"
    assert breaks[0].next_diagram_id == "d2"
    # d1 placed on page 0; d2 placed on page 1
    diagrams_out = [f for f in out if isinstance(f, DiagramFragment)]
    assert diagrams_out[0].placement.page_index == 0
    assert diagrams_out[1].placement.page_index == 1


# ---------------------------------------------------------------------------
# Writer marker <<NEW_PAGE>> emits a PageBreakFragment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_page_marker_emits_page_break_fragment():
    cfg = LayoutConfig()
    measurement = FakeMeasurement(default_height=50.0)
    composer = ManifestComposer(
        diagrams_by_id={"d1": _diagram("d1")},
        layout_config=cfg,
        measurement=measurement,  # type: ignore[arg-type]
    )
    fragments = [
        DiagramFragment(kind="show_diagram", diagram_id="d1"),
        TextEntryFragment(kind="text_entry", id="t1", text="before"),
        NewPageFragment(kind="new_page", carry_forward_ids=["t1"]),
        TextEntryFragment(kind="text_entry", id="t2", text="after"),
    ]
    out = await composer.compose(fragments)
    composer.flush()

    # NewPageFragment should be REPLACED by PageBreakFragment, not preserved.
    assert all(not isinstance(f, NewPageFragment) for f in out)
    breaks = [f for f in out if isinstance(f, PageBreakFragment)]
    assert len(breaks) == 1
    assert breaks[0].reason == "writer_marker"
    assert breaks[0].notebook_carry_forward_ids == ["t1"]


# ---------------------------------------------------------------------------
# Full mixed scenario: 12 blocks + 2 diagrams + 1 writer marker
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mixed_chapter_produces_sensible_pages():
    """A realistic chapter-shaped fragment list: should produce multiple
    pages, all blocks placed, no missing placements."""
    cfg = LayoutConfig()
    # Big blocks → forces overflow. 200 each + spacing 12 = 212. ~3 per page.
    measurement = FakeMeasurement(default_height=200.0)
    dictionary = {
        "el_hyp": {"role": "hypotenuse", "bounds": [200, 200, 200, 5]},
    }
    diagrams = {
        "d1": _diagram("d1", dictionary=dictionary),
        "d2": _diagram("d2"),
    }
    composer = ManifestComposer(
        diagrams_by_id=diagrams,
        layout_config=cfg,
        measurement=measurement,  # type: ignore[arg-type]
        topic_id="chapter-5",
    )

    fragments = [
        DiagramFragment(kind="show_diagram", diagram_id="d1"),
        SectionFragment(kind="section", id="s1", title="Newton's Laws"),
        TextEntryFragment(kind="text_entry", id="t1", text="block 1"),
        EquationFragment(kind="equation", id="eq-1", latex="F = ma"),
        StepFragment(kind="step", id="st-1", text="Step one", indent=0),
        KeyPointFragment(kind="key_point", id="k-1", text="key 1"),
        TextEntryFragment(kind="text_entry", id="t2", text="block 2"),
        AnswerFragment(kind="answer", id="ans-1", text="answer 1"),
        NewPageFragment(kind="new_page"),
        DiagramFragment(kind="show_diagram", diagram_id="d2"),
        TextEntryFragment(kind="text_entry", id="t3", text="block 3"),
        EquationFragment(kind="equation", id="eq-2", latex="v = u + at"),
        KeyPointFragment(kind="key_point", id="k-2", text="key 2"),
    ]
    out = await composer.compose(fragments)
    composer.flush()

    # Sanity: every notebook fragment in `out` has placement stamped.
    notebook_kinds = (
        SectionFragment,
        EquationFragment,
        StepFragment,
        KeyPointFragment,
        TextEntryFragment,
        AnswerFragment,
    )
    nb_fragments = [f for f in out if isinstance(f, notebook_kinds)]
    assert (
        len(nb_fragments) == 10
    )  # all originals (10 notebook fragments) make it through
    for f in nb_fragments:
        assert f.placement is not None
        assert f.placement.measured is True

    # Every diagram has placement + bounds (where dictionary present).
    diagrams_out = [f for f in out if isinstance(f, DiagramFragment)]
    assert len(diagrams_out) == 2
    for d in diagrams_out:
        assert d.placement is not None

    # PageBreaks: at least 2 (one from writer_marker + one+ from overflow).
    breaks = [f for f in out if isinstance(f, PageBreakFragment)]
    assert len(breaks) >= 2
    reasons = {b.reason for b in breaks}
    assert "writer_marker" in reasons
    assert "text_overflow" in reasons or "new_diagram" in reasons

    # PageSummary list monotonic page_indices.
    pages = composer.last_report.pages
    assert len(pages) >= 3
    indices = [p.page_index for p in pages]
    assert indices == sorted(indices)
    assert indices[0] == 0
    # Topic id propagated.
    assert all(p.topic_id == "chapter-5" for p in pages)


# ---------------------------------------------------------------------------
# Layout disabled (Phase 2 mode) — no placement, no PageBreaks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_layout_disabled_phase2_behavior_unchanged():
    """With no layout_config + measurement, the composer behaves exactly
    like Phase 2 — no placement stamping, no PageBreakFragments."""
    diagrams = {
        "d1": _diagram("d1", dictionary={"el": {"role": "r", "bounds": [0, 0, 10, 10]}})
    }
    composer = ManifestComposer(diagrams_by_id=diagrams)
    fragments = [
        DiagramFragment(kind="show_diagram", diagram_id="d1"),
        TextEntryFragment(kind="text_entry", id="t1", text="hello"),
        NewPageFragment(kind="new_page"),
    ]
    out = await composer.compose(fragments)
    # No PageBreakFragments injected
    assert all(not isinstance(f, PageBreakFragment) for f in out)
    # NewPage passes through (handled by Phase 2 walker as a no-op)
    assert any(isinstance(f, NewPageFragment) for f in out)
    # Notebook fragments have no placement
    notebook_fragments = [f for f in out if isinstance(f, TextEntryFragment)]
    assert all(f.placement is None for f in notebook_fragments)
    # No pages recorded
    assert composer.last_report.pages == []


# ---------------------------------------------------------------------------
# Annotations + layout coexist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_focus_coexists_with_layout():
    """Doc-18 spotlight focus should still validate + emit when layout is on.
    Bonus: per-page annotations_count should reflect emitted focus events."""
    cfg = LayoutConfig()
    measurement = FakeMeasurement(default_height=50.0)
    dictionary = {
        "el_hyp": {"role": "hypotenuse", "bounds": [200, 200, 200, 5]},
        "el_theta": {"role": "theta", "bounds": [220, 380, 40, 20]},
    }
    diagrams = {"d1": _diagram("d1", dictionary=dictionary)}
    composer = ManifestComposer(
        diagrams_by_id=diagrams,
        layout_config=cfg,
        measurement=measurement,  # type: ignore[arg-type]
    )

    fragments = [
        DiagramFragment(kind="show_diagram", diagram_id="d1"),
        TextFragment(kind="text", text="some narration"),
        FocusFragment(kind="focus", role="hypotenuse", text="hyp"),
        TextFragment(kind="text", text="more"),
        FocusFragment(kind="focus", role="theta"),
    ]
    out = await composer.compose(fragments)
    composer.flush()

    focuses = [f for f in out if isinstance(f, FocusFragment)]
    assert len(focuses) == 2
    # Annotations count visible in page summary (bumped per focus emit).
    pages = composer.last_report.pages
    assert pages[0].annotations_count >= 2


@pytest.mark.asyncio
async def test_legacy_pin_dropped_with_layout():
    """Legacy PIN fragments must still drop silently when layout is on."""
    cfg = LayoutConfig()
    measurement = FakeMeasurement(default_height=50.0)
    dictionary = {
        "el_hyp": {"role": "hypotenuse", "bounds": [200, 200, 200, 5]},
    }
    diagrams = {"d1": _diagram("d1", dictionary=dictionary)}
    composer = ManifestComposer(
        diagrams_by_id=diagrams,
        layout_config=cfg,
        measurement=measurement,  # type: ignore[arg-type]
    )

    fragments = [
        DiagramFragment(kind="show_diagram", diagram_id="d1"),
        PinFragment(kind="pin", id="pin-1", role="hypotenuse", text="hyp"),
    ]
    out = await composer.compose(fragments)
    composer.flush()

    assert not any(isinstance(f, PinFragment) for f in out)
    assert composer.last_report.drops_by_reason.get("legacy_annotation_deprecated") == 1
