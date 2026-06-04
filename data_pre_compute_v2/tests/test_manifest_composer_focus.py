"""Unit tests for the doc-18 spotlight ManifestComposer + doc-19 primitives.

Each test asserts ONE policy of the FOCUS / UNFOCUS / RESET_FOCUS surface
plus the back-compat behavior for legacy PIN/CALLOUT/etc. markers. Test
data uses a minimal `Diagram` shape — the composer only reads
`diagram.render_data["dictionary"]`, so we mock with SimpleNamespace.

Doc 19 §12 added four new primitives (TRACE / MARK / POINT / WRITE_MARGIN).
Those tests live in the last section of this file.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from lecture_pipeline_v2.curriculum.manifest_composer import ManifestComposer
from lecture_pipeline_v2.tts.chunker import (
    ClearAnnotationsFragment,
    DiagramFragment,
    FocusFragment,
    HighlightFragment,
    MarkPointFragment,
    PinFragment,
    PointAtFragment,
    TextFragment,
    TraceFragment,
    UnfocusFragment,
    WriteMarginFragment,
    split_script,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _diagram(diagram_id: str, dictionary: dict) -> SimpleNamespace:
    return SimpleNamespace(
        diagram_id=diagram_id,
        render_data={"dictionary": dictionary},
    )


@pytest.fixture
def diagrams_by_id() -> dict[str, SimpleNamespace]:
    dictionary = {
        "el_hyp": {
            "role": "hypotenuse",
            "semantic": "the slanted side",
            "position": "center",
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
    return {"d1": _diagram("d1", dictionary)}


def _show(d: str) -> DiagramFragment:
    return DiagramFragment(kind="show_diagram", diagram_id=d)


# ---------------------------------------------------------------------------
# FOCUS — happy path + validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_focus_emits_event(diagrams_by_id):
    fragments = [
        _show("d1"),
        FocusFragment(kind="focus", role="hypotenuse", text="hypotenuse"),
    ]
    composer = ManifestComposer(diagrams_by_id)
    out = await composer.compose(fragments)

    focuses = [f for f in out if isinstance(f, FocusFragment)]
    assert len(focuses) == 1
    assert focuses[0].diagram_id == "d1"
    assert focuses[0].role == "hypotenuse"
    assert focuses[0].text == "hypotenuse"
    assert composer.last_report.emitted >= 1


@pytest.mark.asyncio
async def test_focus_replaces_previous_focus(diagrams_by_id):
    """A second FOCUS on a different role is emitted (frontend swaps focus)."""
    fragments = [
        _show("d1"),
        FocusFragment(kind="focus", role="hypotenuse"),
        FocusFragment(kind="focus", role="opposite_side"),
    ]
    composer = ManifestComposer(diagrams_by_id)
    out = await composer.compose(fragments)

    focuses = [f for f in out if isinstance(f, FocusFragment)]
    assert len(focuses) == 2
    assert [f.role for f in focuses] == ["hypotenuse", "opposite_side"]


@pytest.mark.asyncio
async def test_focus_re_emits_on_same_role(diagrams_by_id):
    """Re-FOCUS on the same role is allowed (re-attention flash)."""
    fragments = [
        _show("d1"),
        FocusFragment(kind="focus", role="hypotenuse"),
        FocusFragment(kind="focus", role="hypotenuse"),
    ]
    composer = ManifestComposer(diagrams_by_id)
    out = await composer.compose(fragments)

    focuses = [f for f in out if isinstance(f, FocusFragment)]
    assert len(focuses) == 2


@pytest.mark.asyncio
async def test_focus_unknown_role_drops(diagrams_by_id):
    fragments = [
        _show("d1"),
        FocusFragment(kind="focus", role="not_a_role"),
    ]
    composer = ManifestComposer(diagrams_by_id)
    out = await composer.compose(fragments)
    assert not any(isinstance(f, FocusFragment) for f in out)
    assert composer.last_report.drops_by_reason.get("role_unknown") == 1


@pytest.mark.asyncio
async def test_focus_no_active_diagram_drops(diagrams_by_id):
    fragments = [FocusFragment(kind="focus", role="hypotenuse")]
    composer = ManifestComposer(diagrams_by_id)
    out = await composer.compose(fragments)
    assert not any(isinstance(f, FocusFragment) for f in out)
    assert composer.last_report.drops_by_reason.get("no_active_diagram") == 1


@pytest.mark.asyncio
async def test_focus_empty_role_drops(diagrams_by_id):
    fragments = [
        _show("d1"),
        FocusFragment(kind="focus", role=""),
    ]
    composer = ManifestComposer(diagrams_by_id)
    out = await composer.compose(fragments)
    assert not any(isinstance(f, FocusFragment) for f in out)
    assert composer.last_report.drops_by_reason.get("focus_empty_role") == 1


# ---------------------------------------------------------------------------
# UNFOCUS
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unfocus_clears_focus(diagrams_by_id):
    fragments = [
        _show("d1"),
        FocusFragment(kind="focus", role="hypotenuse"),
        UnfocusFragment(kind="unfocus"),
    ]
    composer = ManifestComposer(diagrams_by_id)
    out = await composer.compose(fragments)
    unfocuses = [f for f in out if isinstance(f, UnfocusFragment)]
    assert len(unfocuses) == 1
    assert unfocuses[0].diagram_id == "d1"


@pytest.mark.asyncio
async def test_unfocus_no_focus_drops(diagrams_by_id):
    """UNFOCUS with no current focus is a no-op (dropped)."""
    fragments = [
        _show("d1"),
        UnfocusFragment(kind="unfocus"),
    ]
    composer = ManifestComposer(diagrams_by_id)
    out = await composer.compose(fragments)
    assert not any(isinstance(f, UnfocusFragment) for f in out)
    assert composer.last_report.drops_by_reason.get("unfocus_no_focus") == 1


@pytest.mark.asyncio
async def test_unfocus_no_active_diagram_drops(diagrams_by_id):
    fragments = [UnfocusFragment(kind="unfocus")]
    composer = ManifestComposer(diagrams_by_id)
    out = await composer.compose(fragments)
    assert not any(isinstance(f, UnfocusFragment) for f in out)
    assert composer.last_report.drops_by_reason.get("no_active_diagram") == 1


# ---------------------------------------------------------------------------
# RESET_FOCUS (alias: CLEAR_ANNOTATIONS)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_focus_clears_all_state(diagrams_by_id):
    fragments = [
        _show("d1"),
        FocusFragment(kind="focus", role="hypotenuse"),
        ClearAnnotationsFragment(kind="clear_annotations"),
        # After reset, a re-FOCUS still emits.
        FocusFragment(kind="focus", role="hypotenuse"),
    ]
    composer = ManifestComposer(diagrams_by_id)
    out = await composer.compose(fragments)
    focuses = [f for f in out if isinstance(f, FocusFragment)]
    clears = [f for f in out if isinstance(f, ClearAnnotationsFragment)]
    assert len(focuses) == 2
    assert len(clears) == 1
    assert clears[0].diagram_id == "d1"


@pytest.mark.asyncio
async def test_reset_focus_before_diagram_drops(diagrams_by_id):
    fragments = [ClearAnnotationsFragment(kind="clear_annotations")]
    composer = ManifestComposer(diagrams_by_id)
    out = await composer.compose(fragments)
    assert not out
    assert composer.last_report.drops_by_reason.get("clear_no_active_diagram") == 1


# ---------------------------------------------------------------------------
# RESET_FOCUS marker parses to ClearAnnotationsFragment
# ---------------------------------------------------------------------------


def test_reset_focus_marker_parses_to_clear_fragment():
    fragments = split_script("<<RESET_FOCUS>>")
    assert len(fragments) == 1
    assert isinstance(fragments[0], ClearAnnotationsFragment)


def test_focus_marker_parses_with_label():
    fragments = split_script("<<FOCUS:hypotenuse|text=slanted side>>")
    assert len(fragments) == 1
    assert isinstance(fragments[0], FocusFragment)
    assert fragments[0].role == "hypotenuse"
    assert fragments[0].text == "slanted side"


def test_unfocus_marker_parses():
    fragments = split_script("<<UNFOCUS>>")
    assert len(fragments) == 1
    assert isinstance(fragments[0], UnfocusFragment)


# ---------------------------------------------------------------------------
# Legacy marker back-compat: chunker parses, walker drops
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_legacy_pin_marker_dropped_silently(diagrams_by_id):
    """Old PIN markers in narration parse to PinFragment but the walker
    drops them (deprecated; spotlight redesign uses FOCUS)."""
    fragments = [
        _show("d1"),
        PinFragment(kind="pin", id="pin-1", role="hypotenuse", text="x"),
    ]
    composer = ManifestComposer(diagrams_by_id)
    out = await composer.compose(fragments)
    assert not any(isinstance(f, PinFragment) for f in out)
    assert composer.last_report.drops_by_reason.get("legacy_annotation_deprecated") == 1


@pytest.mark.asyncio
async def test_legacy_highlight_dropped_silently(diagrams_by_id):
    fragments = [
        _show("d1"),
        HighlightFragment(kind="highlight", role="hypotenuse"),
    ]
    composer = ManifestComposer(diagrams_by_id)
    out = await composer.compose(fragments)
    assert not any(isinstance(f, HighlightFragment) for f in out)
    assert composer.last_report.drops_by_reason.get("legacy_annotation_deprecated") == 1


@pytest.mark.asyncio
async def test_legacy_warning_logged_once(diagrams_by_id, caplog):
    fragments = [
        _show("d1"),
        PinFragment(kind="pin", id="p1", role="hypotenuse", text="x"),
        PinFragment(kind="pin", id="p2", role="opposite_side", text="y"),
        HighlightFragment(kind="highlight", role="hypotenuse"),
    ]
    composer = ManifestComposer(diagrams_by_id)
    with caplog.at_level("WARNING"):
        await composer.compose(fragments)
    legacy_warnings = [
        r for r in caplog.records if "legacy annotation markers" in r.getMessage()
    ]
    # One-shot per walker.
    assert len(legacy_warnings) == 1
    # All three legacy fragments still get counted in drops_by_reason.
    assert composer.last_report.drops_by_reason.get("legacy_annotation_deprecated") == 3


# ---------------------------------------------------------------------------
# Diagram_id stamping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_walker_stamps_diagram_id_on_focus(diagrams_by_id):
    fragments = [
        _show("d1"),
        FocusFragment(kind="focus", role="hypotenuse"),
    ]
    composer = ManifestComposer(diagrams_by_id)
    out = await composer.compose(fragments)
    focuses = [f for f in out if isinstance(f, FocusFragment)]
    for f in focuses:
        assert f.diagram_id == "d1"


# ---------------------------------------------------------------------------
# Diagrams without a dictionary — focus drops
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_diagram_without_dictionary_drops_focus():
    legacy = SimpleNamespace(diagram_id="legacy", render_data={})
    diagrams_by_id = {"legacy": legacy}
    fragments = [
        _show("legacy"),
        FocusFragment(kind="focus", role="hypotenuse"),
    ]
    composer = ManifestComposer(diagrams_by_id)
    out = await composer.compose(fragments)
    assert not any(isinstance(f, FocusFragment) for f in out)
    assert composer.last_report.drops_by_reason.get("role_unknown", 0) == 1


# ---------------------------------------------------------------------------
# Text fragments still advance cumulative_audio_ms (layout look-ahead uses it)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_walker_stamps_presentation_mode_on_diagram_fragment():
    """Doc 18 §4.3: when the Diagram has a presentation_mode, the walker
    stamps it onto the DiagramFragment so the audio_pipeline can carry it
    into ShowDiagramEvent."""
    diagram = SimpleNamespace(
        diagram_id="d_build",
        render_data={
            "dictionary": {
                "el_a": {"role": "hypotenuse"},
            }
        },
        presentation_mode="build_up",
    )
    composer = ManifestComposer({"d_build": diagram})
    out = await composer.compose([_show("d_build")])
    show = next(f for f in out if isinstance(f, DiagramFragment))
    assert show.presentation_mode == "build_up"


@pytest.mark.asyncio
async def test_walker_presentation_mode_unset_when_missing():
    """When Diagram has no presentation_mode field, frag.presentation_mode
    stays None — backwards-compat for older Diagram objects."""
    diagram = SimpleNamespace(
        diagram_id="d_legacy",
        render_data={
            "dictionary": {"el_a": {"role": "hypotenuse"}},
        },
    )
    composer = ManifestComposer({"d_legacy": diagram})
    out = await composer.compose([_show("d_legacy")])
    show = next(f for f in out if isinstance(f, DiagramFragment))
    assert show.presentation_mode is None


@pytest.mark.asyncio
async def test_text_advances_cumulative_audio_ms(diagrams_by_id):
    fragments = [
        _show("d1"),
        TextFragment(kind="text", text="A" * 100),
        FocusFragment(kind="focus", role="hypotenuse"),
    ]
    composer = ManifestComposer(diagrams_by_id)
    out = await composer.compose(fragments)
    # Focus still emits even though audio_ms has advanced — no cooldown
    # anymore. This is the structural simplification doc 18 promises.
    focuses = [f for f in out if isinstance(f, FocusFragment)]
    assert len(focuses) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Doc 19 §12 — new live-annotation primitives
# ─────────────────────────────────────────────────────────────────────────────


# TRACE ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trace_emits_event_on_valid_element_id(diagrams_by_id):
    fragments = [
        _show("d1"),
        TraceFragment(kind="trace", element_id="el_hyp", duration_ms=2000),
    ]
    composer = ManifestComposer(diagrams_by_id)
    out = await composer.compose(fragments)
    traces = [f for f in out if isinstance(f, TraceFragment)]
    assert len(traces) == 1
    assert traces[0].diagram_id == "d1"
    assert traces[0].element_id == "el_hyp"
    assert traces[0].duration_ms == 2000


@pytest.mark.asyncio
async def test_trace_drops_unknown_element_id(diagrams_by_id):
    fragments = [
        _show("d1"),
        TraceFragment(kind="trace", element_id="not-there"),
    ]
    composer = ManifestComposer(diagrams_by_id)
    out = await composer.compose(fragments)
    assert not any(isinstance(f, TraceFragment) for f in out)
    assert composer.last_report.drops_by_reason.get("element_id_unknown") == 1


@pytest.mark.asyncio
async def test_trace_drops_no_active_diagram(diagrams_by_id):
    fragments = [TraceFragment(kind="trace", element_id="el_hyp")]
    composer = ManifestComposer(diagrams_by_id)
    out = await composer.compose(fragments)
    assert not any(isinstance(f, TraceFragment) for f in out)
    assert composer.last_report.drops_by_reason.get("no_active_diagram") == 1


def test_trace_marker_parses():
    fragments = split_script("<<TRACE:el_hyp|duration_ms=2000>>")
    assert len(fragments) == 1
    assert isinstance(fragments[0], TraceFragment)
    assert fragments[0].element_id == "el_hyp"
    assert fragments[0].duration_ms == 2000


# MARK -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_point_emits_with_active_diagram(diagrams_by_id):
    fragments = [
        _show("d1"),
        MarkPointFragment(
            kind="mark_point",
            point_kind="cross",
            x=0.5,
            y=0.3,
            label="ground",
        ),
    ]
    composer = ManifestComposer(diagrams_by_id)
    out = await composer.compose(fragments)
    marks = [f for f in out if isinstance(f, MarkPointFragment)]
    assert len(marks) == 1
    assert marks[0].diagram_id == "d1"
    assert marks[0].point_kind == "cross"
    assert marks[0].x == 0.5
    assert marks[0].label == "ground"


@pytest.mark.asyncio
async def test_mark_point_drops_no_active_diagram(diagrams_by_id):
    fragments = [
        MarkPointFragment(kind="mark_point", x=0.1, y=0.2),
    ]
    composer = ManifestComposer(diagrams_by_id)
    out = await composer.compose(fragments)
    assert not any(isinstance(f, MarkPointFragment) for f in out)
    assert composer.last_report.drops_by_reason.get("no_active_diagram") == 1


def test_mark_marker_parses():
    fragments = split_script("<<MARK:dot|x=0.5|y=0.3|label=ground>>")
    assert len(fragments) == 1
    assert isinstance(fragments[0], MarkPointFragment)
    assert fragments[0].point_kind == "dot"
    assert fragments[0].x == 0.5
    assert fragments[0].y == 0.3
    assert fragments[0].label == "ground"


def test_mark_marker_invalid_kind_falls_back_to_dot():
    fragments = split_script("<<MARK:bogus|x=0|y=0>>")
    assert isinstance(fragments[0], MarkPointFragment)
    assert fragments[0].point_kind == "dot"


# POINT ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_point_at_emits_with_valid_element_id(diagrams_by_id):
    fragments = [
        _show("d1"),
        PointAtFragment(kind="point_at", element_id="el_theta", from_side="top"),
    ]
    composer = ManifestComposer(diagrams_by_id)
    out = await composer.compose(fragments)
    points = [f for f in out if isinstance(f, PointAtFragment)]
    assert len(points) == 1
    assert points[0].diagram_id == "d1"
    assert points[0].element_id == "el_theta"
    assert points[0].from_side == "top"


@pytest.mark.asyncio
async def test_point_at_drops_unknown_element_id(diagrams_by_id):
    fragments = [
        _show("d1"),
        PointAtFragment(kind="point_at", element_id="ghost"),
    ]
    composer = ManifestComposer(diagrams_by_id)
    out = await composer.compose(fragments)
    assert not any(isinstance(f, PointAtFragment) for f in out)
    assert composer.last_report.drops_by_reason.get("element_id_unknown") == 1


def test_point_marker_parses():
    fragments = split_script("<<POINT:el_hyp|from_side=right>>")
    assert len(fragments) == 1
    assert isinstance(fragments[0], PointAtFragment)
    assert fragments[0].element_id == "el_hyp"
    assert fragments[0].from_side == "right"


# WRITE_MARGIN ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_margin_emits_with_valid_anchor(diagrams_by_id):
    fragments = [
        _show("d1"),
        WriteMarginFragment(
            kind="write_margin",
            anchor_element_id="el_adj",
            side="right",
            text="= b cos θ",
        ),
    ]
    composer = ManifestComposer(diagrams_by_id)
    out = await composer.compose(fragments)
    notes = [f for f in out if isinstance(f, WriteMarginFragment)]
    assert len(notes) == 1
    assert notes[0].diagram_id == "d1"
    assert notes[0].anchor_element_id == "el_adj"
    assert notes[0].text == "= b cos θ"


@pytest.mark.asyncio
async def test_write_margin_drops_unknown_anchor(diagrams_by_id):
    fragments = [
        _show("d1"),
        WriteMarginFragment(
            kind="write_margin",
            anchor_element_id="ghost",
            text="something",
        ),
    ]
    composer = ManifestComposer(diagrams_by_id)
    out = await composer.compose(fragments)
    assert not any(isinstance(f, WriteMarginFragment) for f in out)
    assert composer.last_report.drops_by_reason.get("element_id_unknown") == 1


@pytest.mark.asyncio
async def test_write_margin_drops_empty_text(diagrams_by_id):
    fragments = [
        _show("d1"),
        WriteMarginFragment(
            kind="write_margin",
            anchor_element_id="el_hyp",
            text="   ",
        ),
    ]
    composer = ManifestComposer(diagrams_by_id)
    out = await composer.compose(fragments)
    assert not any(isinstance(f, WriteMarginFragment) for f in out)
    assert composer.last_report.drops_by_reason.get("write_margin_empty_text") == 1


def test_write_margin_marker_parses():
    fragments = split_script("<<WRITE_MARGIN:el_adj|side=left|text== b cos theta>>")
    assert len(fragments) == 1
    assert isinstance(fragments[0], WriteMarginFragment)
    assert fragments[0].anchor_element_id == "el_adj"
    assert fragments[0].side == "left"
    assert "b cos theta" in fragments[0].text


# ─────────────────────────────────────────────────────────────────────────────
# Doc 19 §A-3 — FocusEvent element_id is now the preferred selector
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_focus_walker_stamps_element_id_from_role(diagrams_by_id):
    """The walker should resolve the role through the diagram's dictionary
    and stamp `element_id` on the FocusFragment for the audio_pipeline to
    populate FocusEvent.target_element_id with."""
    fragments = [
        _show("d1"),
        FocusFragment(kind="focus", role="hypotenuse"),
    ]
    composer = ManifestComposer(diagrams_by_id)
    out = await composer.compose(fragments)
    focuses = [f for f in out if isinstance(f, FocusFragment)]
    assert len(focuses) == 1
    assert focuses[0].element_id == "el_hyp"
    assert focuses[0].role == "hypotenuse"
    assert focuses[0].diagram_id == "d1"


@pytest.mark.asyncio
async def test_focus_accepts_element_id_value(diagrams_by_id):
    """The narrator emits FOCUS with the stable element_id (doc 19 §A-3) —
    `<<FOCUS:el_hyp>>` — which the chunker carries on `.role`. The walker must
    resolve it by element_id, not drop it as an unknown role. This is the bug
    that killed the lecture spotlight (focus dropped `role_unknown` while
    trace/point_at, validated by element_id, survived)."""
    fragments = [
        _show("d1"),
        FocusFragment(kind="focus", role="el_hyp", text="the slanted side"),
    ]
    composer = ManifestComposer(diagrams_by_id)
    out = await composer.compose(fragments)
    focuses = [f for f in out if isinstance(f, FocusFragment)]
    assert len(focuses) == 1
    assert focuses[0].element_id == "el_hyp"
    assert focuses[0].role == "hypotenuse"  # back-filled from the dictionary
    assert focuses[0].diagram_id == "d1"
    assert composer.last_report.drops_by_reason.get("role_unknown") is None


def test_focus_event_accepts_element_id_only():
    """FocusEvent constructed from element_id alone is valid (the canonical
    new shape — the only thing the frontend needs to resolve bounds)."""
    from lecture_pipeline_v2.curriculum.models import FocusEvent

    event = FocusEvent(diagram_id="d1", target_element_id="el_hyp")
    assert event.target_element_id == "el_hyp"
    assert event.target_role is None
    assert event.text == ""


def test_focus_event_accepts_role_only_back_compat():
    """Legacy FocusEvent JSON from pre-A-3 extraction files only carries
    target_role. Must still deserialize."""
    from lecture_pipeline_v2.curriculum.models import FocusEvent

    event = FocusEvent(diagram_id="d1", target_role="hypotenuse")
    assert event.target_role == "hypotenuse"
    assert event.target_element_id is None


def test_focus_event_accepts_both_fields_populated():
    from lecture_pipeline_v2.curriculum.models import FocusEvent

    event = FocusEvent(
        diagram_id="d1",
        target_element_id="el_hyp",
        target_role="hypotenuse",
        text="slanted side",
    )
    assert event.target_element_id == "el_hyp"
    assert event.target_role == "hypotenuse"


def test_focus_event_rejects_no_target():
    """FocusEvent with neither selector is a programmer error."""
    from pydantic import ValidationError

    from lecture_pipeline_v2.curriculum.models import FocusEvent

    with pytest.raises(ValidationError) as exc_info:
        FocusEvent(diagram_id="d1")
    assert "target_element_id" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Co-highlight — multi-element FOCUS (<<FOCUS:a+b>>) end-to-end
# ---------------------------------------------------------------------------


def test_chunker_parses_co_highlight_focus():
    """`<<FOCUS:a+b>>` carries both ids; a single-id focus stays single."""
    multi = next(
        f for f in split_script("<<FOCUS:el_hyp+el_opp>>") if f.kind == "focus"
    )
    assert multi.element_ids == ["el_hyp", "el_opp"]
    assert multi.role == "el_hyp"
    single = next(f for f in split_script("<<FOCUS:el_hyp>>") if f.kind == "focus")
    assert single.element_ids == []
    assert single.role == "el_hyp"


@pytest.mark.asyncio
async def test_co_highlight_resolves_all_ids(diagrams_by_id):
    """A co-highlight FOCUS resolves every id; the first mirrors into
    element_id for single-target consumers."""
    fragments = [
        _show("d1"),
        FocusFragment(kind="focus", role="el_hyp", element_ids=["el_hyp", "el_opp"]),
    ]
    out = await ManifestComposer(diagrams_by_id).compose(fragments)
    focus = next(f for f in out if isinstance(f, FocusFragment))
    assert focus.element_ids == ["el_hyp", "el_opp"]
    assert focus.element_id == "el_hyp"


@pytest.mark.asyncio
async def test_co_highlight_resolves_roles(diagrams_by_id):
    """Co-highlight targets given as ROLE names resolve to element_ids."""
    fragments = [
        _show("d1"),
        FocusFragment(
            kind="focus",
            role="hypotenuse",
            element_ids=["hypotenuse", "opposite_side"],
        ),
    ]
    out = await ManifestComposer(diagrams_by_id).compose(fragments)
    focus = next(f for f in out if isinstance(f, FocusFragment))
    assert focus.element_ids == ["el_hyp", "el_opp"]


@pytest.mark.asyncio
async def test_co_highlight_drops_invalid_keeps_valid(diagrams_by_id):
    """An unresolvable id in a co-highlight set is dropped; valid ones survive."""
    fragments = [
        _show("d1"),
        FocusFragment(kind="focus", role="el_hyp", element_ids=["el_hyp", "nope"]),
    ]
    out = await ManifestComposer(diagrams_by_id).compose(fragments)
    focus = next(f for f in out if isinstance(f, FocusFragment))
    assert focus.element_ids == ["el_hyp"]


@pytest.mark.asyncio
async def test_co_highlight_all_invalid_drops_fragment(diagrams_by_id):
    """If NO id in a co-highlight set resolves, the whole FOCUS drops."""
    fragments = [
        _show("d1"),
        FocusFragment(kind="focus", role="nope1", element_ids=["nope1", "nope2"]),
    ]
    out = await ManifestComposer(diagrams_by_id).compose(fragments)
    assert not [f for f in out if isinstance(f, FocusFragment)]


def test_focus_event_accepts_target_element_ids_only():
    """FocusEvent validates with only the co-highlight list set."""
    from lecture_pipeline_v2.curriculum.models import FocusEvent

    event = FocusEvent(diagram_id="d1", target_element_ids=["el_hyp", "el_opp"])
    assert event.target_element_ids == ["el_hyp", "el_opp"]
