"""Tests for LayoutPlanner (Phase 3) — uses a fake MeasurementService.

Covers:
  - initial_page_state geometry from LayoutConfig
  - place_text: fit, overflow → was_break, cursor advancement
  - place_diagram: viewBox → page-coord transform; element_bounds; was_break on diff diagram
  - decide_slide_action: 3 trigger paths × references / no-references / next-diagram
  - open_new_page: keep / swap / release slide handling
  - select_carry_forward_ids: ANSWER/KEY pickup, SECTION cutoff
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from lecture_pipeline_v2.config import LayoutConfig
from lecture_pipeline_v2.curriculum.manifest_composer.policies.layout import (
    BlockPlacement,
    LayoutPlanner,
    PageState,
)


class FakeMeasurementService:
    """Deterministic measurement: returns height proportional to content length.

    Each test can override the formula or pre-seed specific values.
    """

    def __init__(self, default_height: float = 30.0):
        self.default_height = default_height
        self._overrides: dict[tuple, dict[str, float]] = {}
        self.calls: list[tuple] = []

    def stub(
        self, block_type: str, content: str, height: float, width: float | None = None
    ):
        self._overrides[(block_type, content)] = {
            "width": width or 540.0,
            "height": height,
        }

    async def measure(self, block_type, content, attrs=None, width_px=None):
        self.calls.append((block_type, content, attrs or {}, width_px))
        if (block_type, content) in self._overrides:
            return dict(self._overrides[(block_type, content)])
        return {"width": width_px or 540.0, "height": self.default_height}


# ---------------------------------------------------------------------------
# Fragment factories (mirroring chunker dataclasses via SimpleNamespace)
# ---------------------------------------------------------------------------


def f_section(id_: str, title: str) -> Any:
    return SimpleNamespace(kind="section", id=id_, title=title)


def f_equation(id_: str, latex: str) -> Any:
    return SimpleNamespace(
        kind="equation", id=id_, latex=latex, align_group=None, boxed=False
    )


def f_step(id_: str, text: str, indent: int = 0) -> Any:
    return SimpleNamespace(kind="step", id=id_, text=text, indent=indent)


def f_key(id_: str, text: str) -> Any:
    return SimpleNamespace(kind="key_point", id=id_, text=text)


def f_text(id_: str, text: str) -> Any:
    return SimpleNamespace(kind="text_entry", id=id_, text=text)


def f_answer(id_: str, text: str) -> Any:
    return SimpleNamespace(kind="answer", id=id_, text=text)


def f_diagram(diagram_id: str) -> Any:
    return SimpleNamespace(kind="show_diagram", diagram_id=diagram_id)


def f_pin(role: str) -> Any:
    return SimpleNamespace(kind="pin", role=role)


def f_pulse(role: str) -> Any:
    return SimpleNamespace(kind="pulse", role=role)


def make_diagram(view_box: str = "0 0 800 600", dictionary: dict | None = None) -> Any:
    render_data = {"viewBox": view_box}
    if dictionary:
        render_data["dictionary"] = dictionary
    return SimpleNamespace(diagram_id="d_test", render_data=render_data)


# ---------------------------------------------------------------------------
# initial_page_state geometry
# ---------------------------------------------------------------------------


def test_initial_page_state_geometry():
    cfg = LayoutConfig()  # use defaults
    planner = LayoutPlanner(cfg, measurement=None)  # type: ignore[arg-type]
    ps = planner.initial_page_state(topic_id="t1")
    assert ps.page_index == 0
    assert ps.topic_id == "t1"
    assert ps.slide.diagram_id is None
    # notebook inner region = (970+30, 50+30) → (1000, 80) top-left; bottom = 50+800-30 = 820
    assert ps.notebook.inner_top == 80.0
    assert ps.notebook.inner_bottom == 820.0
    assert ps.notebook.inner_x == 1000.0
    assert ps.notebook.inner_width == 540.0
    assert ps.notebook.cursor_y == 80.0


# ---------------------------------------------------------------------------
# place_text: fit, overflow, cursor advancement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_place_text_fits_and_advances_cursor():
    cfg = LayoutConfig()
    measurement = FakeMeasurementService(default_height=30.0)
    planner = LayoutPlanner(cfg, measurement=measurement)
    ps = planner.initial_page_state()

    frag = f_text("t1", "hello world")
    placement, was_break = await planner.place_text(frag, ps)
    assert was_break is False
    assert placement is not None
    assert placement.measured is True
    assert placement.rect.x == 1000.0
    assert placement.rect.y == 80.0
    assert placement.rect.height == 30.0
    # cursor advanced by height + block_spacing_px (12 default)
    assert ps.notebook.cursor_y == 80.0 + 30.0 + 12.0  # = 122.0
    assert len(ps.notebook.blocks) == 1


@pytest.mark.asyncio
async def test_place_text_overflow_signals_break():
    """A block that doesn't fit in remaining inner_height triggers was_break."""
    cfg = LayoutConfig()
    measurement = FakeMeasurementService(default_height=900.0)  # huge
    planner = LayoutPlanner(cfg, measurement=measurement)
    ps = planner.initial_page_state()

    frag = f_text("t1", "hello")
    placement, was_break = await planner.place_text(frag, ps)
    assert was_break is True
    assert placement is None
    # Page state must NOT have been mutated.
    assert ps.notebook.cursor_y == 80.0
    assert len(ps.notebook.blocks) == 0


@pytest.mark.asyncio
async def test_place_text_fills_page_then_overflows():
    """Place blocks until they overflow; verify the boundary."""
    cfg = LayoutConfig()
    measurement = FakeMeasurementService(default_height=100.0)
    planner = LayoutPlanner(cfg, measurement=measurement)
    ps = planner.initial_page_state()
    # inner_height = 740. block_spacing = 12. (100 + 12) per block.
    # max fit: cursor_y + 100 <= inner_bottom - safety (820 - 8 = 812)
    # block 1: 80 + 100 = 180 ≤ 812 → fit, cursor → 192
    # block 2: 192 + 100 = 292 → fit, cursor → 304
    # block 3-7 similarly → cursor=80+7*112=864 → exceeds 812 at block 7
    fits = 0
    for i in range(10):
        p, br = await planner.place_text(f_text(f"t{i}", "x"), ps)
        if br:
            break
        fits += 1
    # Should fit ~7 blocks
    assert 6 <= fits <= 8, f"expected 6-8 blocks to fit, got {fits}"


@pytest.mark.asyncio
async def test_place_text_measurement_failure_falls_back():
    """If MeasurementService raises, we should still produce a placement
    with measured=False so the chapter doesn't abort."""

    class FailingMeasurement:
        async def measure(self, *a, **kw):
            raise RuntimeError("playwright crashed")

    cfg = LayoutConfig()
    planner = LayoutPlanner(cfg, measurement=FailingMeasurement())  # type: ignore[arg-type]
    ps = planner.initial_page_state()

    frag = f_text("t1", "short")
    placement, was_break = await planner.place_text(frag, ps)
    assert placement is not None
    assert placement.measured is False
    assert was_break is False


# ---------------------------------------------------------------------------
# place_diagram: viewBox math, element bounds, was_break
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_place_diagram_contain_math():
    """viewBox 800x600 in slide (900x800 with pad=20). Inner = 860x760.
    Scale = min(860/800, 760/600, 1.0) = min(1.075, 1.267, 1.0) = 1.0.
    Placed at center: x=30+20+(860-800)/2=80, y=50+20+(760-600)/2=150.
    """
    cfg = LayoutConfig()
    measurement = FakeMeasurementService()
    planner = LayoutPlanner(cfg, measurement=measurement)
    ps = planner.initial_page_state()

    diagram = make_diagram(
        view_box="0 0 800 600",
        dictionary={
            "el_hyp": {"role": "hypotenuse", "bounds": [200, 200, 200, 5]},
            "el_theta": {"role": "theta_angle", "bounds": [220, 380, 40, 20]},
        },
    )
    frag = f_diagram("d_test")
    placement, bounds, was_break = await planner.place_diagram(frag, diagram, ps)
    assert was_break is False
    assert placement is not None
    assert placement.rect.x == pytest.approx(80.0)
    assert placement.rect.y == pytest.approx(150.0)
    assert placement.rect.width == pytest.approx(800.0)
    assert placement.rect.height == pytest.approx(600.0)
    # Element bounds in page coords: bx*scale + placed_x = 200*1.0 + 80 = 280
    assert bounds is not None
    assert "hypotenuse" in bounds
    assert bounds["hypotenuse"].x == pytest.approx(280.0)
    assert bounds["hypotenuse"].y == pytest.approx(350.0)
    # And slide state updated
    assert ps.slide.diagram_id == "d_test"
    assert ps.slide.placed_rect is not None


@pytest.mark.asyncio
async def test_place_diagram_scales_when_too_wide():
    """A 1200x600 diagram in 860x760 inner → scale = min(860/1200, 760/600, 1.0) = 0.717."""
    cfg = LayoutConfig()
    planner = LayoutPlanner(cfg, measurement=FakeMeasurementService())
    ps = planner.initial_page_state()

    diagram = make_diagram(view_box="0 0 1200 600", dictionary={})
    frag = f_diagram("d_wide")
    placement, _, was_break = await planner.place_diagram(frag, diagram, ps)
    assert was_break is False
    assert placement is not None
    # 1200 * (860/1200) = 860
    assert placement.rect.width == pytest.approx(860.0, abs=0.5)
    # 600 * (860/1200) = 430
    assert placement.rect.height == pytest.approx(430.0, abs=0.5)


@pytest.mark.asyncio
async def test_place_diagram_was_break_on_diff_diagram():
    """If the slide already has a different diagram, was_break=True."""
    cfg = LayoutConfig()
    planner = LayoutPlanner(cfg, measurement=FakeMeasurementService())
    ps = planner.initial_page_state()
    ps.slide.diagram_id = "d_existing"

    frag = f_diagram("d_new")
    placement, bounds, was_break = await planner.place_diagram(frag, make_diagram(), ps)
    assert was_break is True
    assert placement is None
    # Slide state untouched
    assert ps.slide.diagram_id == "d_existing"


@pytest.mark.asyncio
async def test_place_diagram_no_view_box_fallback():
    """Diagram without viewBox should still place at slide inner with measured=False."""
    cfg = LayoutConfig()
    planner = LayoutPlanner(cfg, measurement=FakeMeasurementService())
    ps = planner.initial_page_state()

    diagram = SimpleNamespace(diagram_id="d_novb", render_data={})  # no viewBox
    placement, bounds, was_break = await planner.place_diagram(
        f_diagram("d_novb"), diagram, ps
    )
    assert was_break is False
    assert placement is not None
    assert placement.measured is False


@pytest.mark.asyncio
async def test_place_diagram_same_id_idempotent():
    """Placing the SAME diagram_id again on a page that already has it is a no-op-style success."""
    cfg = LayoutConfig()
    planner = LayoutPlanner(cfg, measurement=FakeMeasurementService())
    ps = planner.initial_page_state()
    ps.slide.diagram_id = "d_same"

    diagram = make_diagram()
    frag = SimpleNamespace(kind="show_diagram", diagram_id="d_same")
    placement, _, was_break = await planner.place_diagram(frag, diagram, ps)
    assert was_break is False
    assert placement is not None


# ---------------------------------------------------------------------------
# decide_slide_action: 3 trigger types × scenarios
# ---------------------------------------------------------------------------


def _planner_with_slide_roles(roles: list[str]) -> tuple[LayoutPlanner, PageState]:
    cfg = LayoutConfig()
    planner = LayoutPlanner(cfg, measurement=None)  # type: ignore[arg-type]
    ps = planner.initial_page_state()
    from lecture_pipeline_v2.curriculum.manifest_composer import geometry as geo

    ps.slide.diagram_id = "d_curr"
    ps.slide.element_bounds = {
        r: geo.Rect(x=0, y=0, width=10, height=10) for r in roles
    }
    return planner, ps


def test_decide_slide_action_new_diagram_always_swaps():
    planner, ps = _planner_with_slide_roles(["hypotenuse"])
    fragments = [f_diagram("d_next")]
    timings = [10_000.0]
    action, next_id = planner.decide_slide_action(
        fragments, timings, current_idx=-1, page_state=ps, trigger_reason="new_diagram"
    )
    # current_idx=-1 means look-ahead starts at index 0 (the diagram).
    assert action == "swap"
    assert next_id == "d_next"


def test_decide_slide_action_text_overflow_with_references_keeps():
    """References to current slide roles within window → keep."""
    planner, ps = _planner_with_slide_roles(["hypotenuse", "theta_angle"])
    # current_idx=0 is a text fragment; reference at idx 2 within window
    fragments = [
        SimpleNamespace(kind="text", text="x"),
        SimpleNamespace(kind="text", text="y"),
        f_pulse("hypotenuse"),
    ]
    timings = [0.0, 1_000.0, 2_000.0]
    action, next_id = planner.decide_slide_action(
        fragments, timings, current_idx=0, page_state=ps, trigger_reason="text_overflow"
    )
    assert action == "keep"
    assert next_id is None


def test_decide_slide_action_text_overflow_no_refs_releases():
    """No references AND a future ShowDiagram → release (slide is leaving anyway)."""
    planner, ps = _planner_with_slide_roles(["hypotenuse"])
    fragments = [
        SimpleNamespace(kind="text", text="x"),
        SimpleNamespace(kind="text", text="y"),
        f_diagram("d_next"),
    ]
    timings = [0.0, 1_000.0, 5_000.0]
    action, next_id = planner.decide_slide_action(
        fragments, timings, current_idx=0, page_state=ps, trigger_reason="text_overflow"
    )
    assert action == "release"
    assert next_id is None  # text_overflow doesn't return next_id


def test_decide_slide_action_text_overflow_no_refs_no_next_keeps():
    """No references AND no upcoming diagram → keep (current slide is still relevant)."""
    planner, ps = _planner_with_slide_roles(["hypotenuse"])
    fragments = [
        SimpleNamespace(kind="text", text="x"),
        SimpleNamespace(kind="text", text="y"),
    ]
    timings = [0.0, 1_000.0]
    action, next_id = planner.decide_slide_action(
        fragments, timings, current_idx=0, page_state=ps, trigger_reason="text_overflow"
    )
    assert action == "keep"


def test_decide_slide_action_writer_marker_swaps_if_imminent():
    planner, ps = _planner_with_slide_roles(["hypotenuse"])
    fragments = [
        SimpleNamespace(kind="new_page"),
        f_diagram("d_next"),
    ]
    timings = [0.0, 3_000.0]
    action, next_id = planner.decide_slide_action(
        fragments, timings, current_idx=0, page_state=ps, trigger_reason="writer_marker"
    )
    assert action == "swap"
    assert next_id == "d_next"


def test_decide_slide_action_writer_marker_keeps_if_no_diagram_ahead():
    planner, ps = _planner_with_slide_roles(["hypotenuse"])
    fragments = [
        SimpleNamespace(kind="new_page"),
        SimpleNamespace(kind="text", text="continuing"),
    ]
    timings = [0.0, 3_000.0]
    action, next_id = planner.decide_slide_action(
        fragments, timings, current_idx=0, page_state=ps, trigger_reason="writer_marker"
    )
    assert action == "keep"


def test_decide_slide_action_lookahead_window_respects_limit():
    """A new diagram beyond the lookahead window does NOT trigger release."""
    planner, ps = _planner_with_slide_roles(["hypotenuse"])
    fragments = [
        SimpleNamespace(kind="text", text="x"),
        f_diagram("d_far_future"),  # at t=100_000ms, way beyond 20s window
    ]
    timings = [0.0, 100_000.0]
    action, next_id = planner.decide_slide_action(
        fragments, timings, current_idx=0, page_state=ps, trigger_reason="text_overflow"
    )
    # No references in window AND no diagram in window → keep
    assert action == "keep"


def test_decide_slide_action_bracket_with_role_in_current_keeps():
    planner, ps = _planner_with_slide_roles(["hypotenuse", "opposite_side"])
    fragments = [
        SimpleNamespace(kind="text", text="x"),
        SimpleNamespace(kind="bracket", role_a="hypotenuse", role_b="other_role"),
    ]
    timings = [0.0, 1_000.0]
    action, _ = planner.decide_slide_action(
        fragments, timings, current_idx=0, page_state=ps, trigger_reason="text_overflow"
    )
    assert action == "keep"


# ---------------------------------------------------------------------------
# open_new_page: keep / swap / release
# ---------------------------------------------------------------------------


def test_open_new_page_keep_carries_slide():
    cfg = LayoutConfig()
    planner = LayoutPlanner(cfg, measurement=None)  # type: ignore[arg-type]
    ps = planner.initial_page_state()
    from lecture_pipeline_v2.curriculum.manifest_composer import geometry as geo

    ps.slide.diagram_id = "d_curr"
    ps.slide.placed_rect = geo.Rect(x=10, y=10, width=100, height=100)
    ps.slide.element_bounds = {"role_x": geo.Rect(x=20, y=20, width=10, height=10)}
    ps.slide.annotations_count = 3
    # Drop some blocks so we can verify notebook resets
    ps.notebook.blocks = [
        BlockPlacement(
            fragment_id="b1",
            block_type="TEXT",
            rect=geo.Rect(x=0, y=0, width=10, height=10),
        )
    ]
    ps.notebook.cursor_y = 200.0

    new = planner.open_new_page(ps, "keep", None, audio_time_ms=5_000.0)
    assert new.page_index == 1
    assert new.slide.diagram_id == "d_curr"
    assert new.slide.placed_rect is not None  # carried
    assert "role_x" in new.slide.element_bounds
    assert new.slide.annotations_count == 0  # reset per-page
    # Notebook reset
    assert new.notebook.blocks == []
    assert new.notebook.cursor_y == new.notebook.inner_top
    assert new.audio_time_ms == 5_000.0


def test_open_new_page_swap_clears_slide():
    cfg = LayoutConfig()
    planner = LayoutPlanner(cfg, measurement=None)  # type: ignore[arg-type]
    ps = planner.initial_page_state()
    from lecture_pipeline_v2.curriculum.manifest_composer import geometry as geo

    ps.slide.diagram_id = "d_old"
    ps.slide.element_bounds = {"role_y": geo.Rect(x=0, y=0, width=5, height=5)}
    new = planner.open_new_page(ps, "swap", "d_new", audio_time_ms=2_000.0)
    assert new.slide.diagram_id is None  # cleared; next ShowDiagram will populate
    assert new.slide.element_bounds == {}


def test_open_new_page_release_clears_slide():
    cfg = LayoutConfig()
    planner = LayoutPlanner(cfg, measurement=None)  # type: ignore[arg-type]
    ps = planner.initial_page_state()
    ps.slide.diagram_id = "d_old"
    new = planner.open_new_page(ps, "release", None, audio_time_ms=1_000.0)
    assert new.slide.diagram_id is None


# ---------------------------------------------------------------------------
# select_carry_forward_ids
# ---------------------------------------------------------------------------


def test_select_carry_forward_picks_recent_answer():
    cfg = LayoutConfig()
    planner = LayoutPlanner(cfg, measurement=None)  # type: ignore[arg-type]
    ps = planner.initial_page_state()
    from lecture_pipeline_v2.curriculum.manifest_composer import geometry as geo

    r = geo.Rect(x=0, y=0, width=10, height=10)
    ps.notebook.blocks = [
        BlockPlacement(fragment_id="t1", block_type="TEXT", rect=r),
        BlockPlacement(fragment_id="ans1", block_type="ANSWER", rect=r),
    ]
    assert planner.select_carry_forward_ids(ps) == ["ans1"]


def test_select_carry_forward_picks_recent_key():
    cfg = LayoutConfig()
    planner = LayoutPlanner(cfg, measurement=None)  # type: ignore[arg-type]
    ps = planner.initial_page_state()
    from lecture_pipeline_v2.curriculum.manifest_composer import geometry as geo

    r = geo.Rect(x=0, y=0, width=10, height=10)
    ps.notebook.blocks = [
        BlockPlacement(fragment_id="key1", block_type="KEY", rect=r),
        BlockPlacement(fragment_id="t1", block_type="TEXT", rect=r),
    ]
    # KEY is older than TEXT; reverse-scan stops at TEXT (which is neither
    # ANSWER/KEY/SECTION), continues; finds KEY.
    assert planner.select_carry_forward_ids(ps) == ["key1"]


def test_select_carry_forward_stops_at_section():
    cfg = LayoutConfig()
    planner = LayoutPlanner(cfg, measurement=None)  # type: ignore[arg-type]
    ps = planner.initial_page_state()
    from lecture_pipeline_v2.curriculum.manifest_composer import geometry as geo

    r = geo.Rect(x=0, y=0, width=10, height=10)
    ps.notebook.blocks = [
        BlockPlacement(fragment_id="ans_old", block_type="ANSWER", rect=r),
        BlockPlacement(fragment_id="sec1", block_type="SECTION", rect=r),
        BlockPlacement(fragment_id="t1", block_type="TEXT", rect=r),
    ]
    # Reverse-scan: TEXT (continue) → SECTION (stop) → never reaches ans_old
    assert planner.select_carry_forward_ids(ps) == []


def test_select_carry_forward_empty_when_none():
    cfg = LayoutConfig()
    planner = LayoutPlanner(cfg, measurement=None)  # type: ignore[arg-type]
    ps = planner.initial_page_state()
    assert planner.select_carry_forward_ids(ps) == []
