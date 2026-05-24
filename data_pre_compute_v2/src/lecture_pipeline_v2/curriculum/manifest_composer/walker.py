"""Fragment-stream walker — holds composer state, applies focus + layout policies.

Doc 18 contract:
- INPUT: list[ScriptFragment] from chunker.split_script()
- OUTPUT: list[ScriptFragment] (focus is validated against the active
  diagram's dictionary; legacy PIN/CALLOUT/BRACKET/HIGHLIGHT/PULSE are
  dropped silently; text/diagram/notebook fragments pass through unchanged).
- The walker stamps `diagram_id = active_diagram_id` onto every focus
  fragment before emitting (chunker doesn't know which diagram is active).

Phase 3 extension (when layout_planner is provided):
- Walker becomes async (measurement requires Playwright via async).
- Pre-computes `fragment_timings: list[float]` (cumulative ms per fragment
  end) so look-ahead decisions can see future fragments in audio time.
- Stamps `placement` onto every notebook fragment + DiagramFragment via
  the LayoutPlanner.
- Injects synthetic PageBreakFragment when overflow / diagram change /
  writer-marker triggers fire.
- Closes each page with a PageSummary in the composer report.

State is per-diagram (focus) AND per-page (layout). Phase 3's PageState
resets at the start of every chapter and on every page break.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ...tts.chunker import (
    AnswerFragment,
    ClearAnnotationsFragment,
    DiagramFragment,
    EquationFragment,
    FocusFragment,
    KeyPointFragment,
    MarkPointFragment,
    NewPageFragment,
    PageBreakFragment,
    PointAtFragment,
    ScriptFragment,
    SectionFragment,
    StepFragment,
    TextEntryFragment,
    TextFragment,
    TraceFragment,
    UnfocusFragment,
    WriteMarginFragment,
)
from ..models import PageSummary
from .policies.layout import LayoutPlanner, NOTEBOOK_FRAGMENT_KINDS, PageState

logger = logging.getLogger(__name__)


# Speech-rate estimate for advancing cumulative_audio_ms from TextFragment
# lengths. Kokoro hits ~12 chars/sec (~83 ms/char). Off by a constant factor
# across all chapters — fine for layout look-ahead.
WPM_CHARS_PER_MS = 1 / 83.0


# ---------------------------------------------------------------------------
# Per-diagram state (rebuilt each ShowDiagram)
# ---------------------------------------------------------------------------


@dataclass
class _PerDiagramState:
    """Doc-18 simplified state: dictionary for role validation, focus pointer.

    Spatial occupancy / persistent budget / transient window were all
    dropped — the frontend resolves role → DOM bounds at render time, and
    the spotlight primitive has no concept of "competing annotations".
    """

    diagram_id: str
    # The diagram's dictionary: element_id → {role, semantic, position, bounds}.
    dictionary: dict[str, dict[str, Any]]
    # role → element_id (lazy index built on first access).
    _role_to_element: dict[str, str] | None = None
    # Currently focused role (last FOCUS), or None if nothing focused.
    focus_role: str | None = None

    def role_to_element_id(self, role: str) -> str | None:
        if self._role_to_element is None:
            idx: dict[str, str] = {}
            for element_id, meta in self.dictionary.items():
                if not isinstance(meta, dict):
                    continue
                r = meta.get("role")
                if isinstance(r, str) and r not in idx:
                    idx[r] = element_id
            self._role_to_element = idx
        return self._role_to_element.get(role)

    def has_role(self, role: str) -> bool:
        return self.role_to_element_id(role) is not None

    def has_element_id(self, element_id: str) -> bool:
        return element_id in self.dictionary


# ---------------------------------------------------------------------------
# Composer report — telemetry on what got emitted vs dropped
# ---------------------------------------------------------------------------


@dataclass
class ComposerReport:
    emitted: int = 0
    dropped: int = 0
    downgraded: int = 0
    drops_by_reason: dict[str, int] = field(default_factory=dict)
    # Phase 3: one PageSummary per page closed. Walker appends at every
    # page-break boundary and at the end of `walk()`.
    pages: list[PageSummary] = field(default_factory=list)
    # Phase 3: count of PageBreakFragments emitted (subset of pages — a
    # single-page chapter has 1 page but 0 breaks).
    page_breaks: int = 0
    breaks_by_reason: dict[str, int] = field(default_factory=dict)

    def record_drop(self, reason: str) -> None:
        self.dropped += 1
        self.drops_by_reason[reason] = self.drops_by_reason.get(reason, 0) + 1

    def record_downgrade(self) -> None:
        self.downgraded += 1

    def record_emit(self) -> None:
        self.emitted += 1

    def record_break(self, reason: str) -> None:
        self.page_breaks += 1
        self.breaks_by_reason[reason] = self.breaks_by_reason.get(reason, 0) + 1

    def summary(self) -> str:
        layout_part = ""
        if self.pages:
            layout_part = (
                f" pages={len(self.pages)} breaks={self.page_breaks}"
                f" by_reason={self.breaks_by_reason}"
            )
        return (
            f"ManifestComposer: emitted={self.emitted} dropped={self.dropped} "
            f"downgraded={self.downgraded} drops_by_reason={self.drops_by_reason}"
            f"{layout_part}"
        )


# ---------------------------------------------------------------------------
# Walker
# ---------------------------------------------------------------------------


class Walker:
    """Walks a fragment stream once; emits a filtered stream + a report.

    If `layout_planner` is provided, also measures + places notebook blocks,
    decides page breaks, and stamps placement metadata onto fragments.
    """

    def __init__(
        self,
        diagrams_by_id: dict[str, Any],
        layout_planner: LayoutPlanner | None = None,
        topic_id: str = "",
    ) -> None:
        self._diagrams_by_id = diagrams_by_id
        self._layout = layout_planner
        self._topic_id = topic_id
        self.report = ComposerReport()
        self._cumulative_audio_ms: int = 0
        self._active: _PerDiagramState | None = None
        # Back-compat: one-shot deprecation log per chapter to avoid
        # spamming when old-marker scripts feed through during transition.
        self._legacy_warned: bool = False
        # Phase 3 state — only used when layout_planner is provided.
        self._page_state: PageState | None = None
        self._fragment_timings: list[float] = []

    async def walk(self, fragments: list[ScriptFragment]) -> list[ScriptFragment]:
        """Walk one fragment batch, applying policies. State persists across
        calls on the same walker (page state, cumulative audio).
        Caller logs `report.summary()` once at the end of the chapter.
        """
        # Precompute look-ahead timings only when layout is enabled.
        if self._layout is not None:
            self._fragment_timings = self._precompute_timings(fragments)
        else:
            self._fragment_timings = []

        out: list[ScriptFragment] = []
        for idx, frag in enumerate(fragments):
            emitted = await self._handle(frag, fragments, idx)
            for f in emitted:
                out.append(f)

        # At the end of a walk(), if layout is enabled and a page state
        # exists, close the current page with a summary.
        # NOTE: we DON'T finalize here if the caller might call walk() again
        # with more fragments for the same chapter (composer state is sticky).
        # The composer's `flush()` does the final close. See composer.py.

        return out

    def flush(self) -> None:
        """Finalize chapter-level state. Currently: append the last open
        page's summary if layout was active. Called by ManifestComposer at
        the end of a chapter's narration."""
        if self._layout is None or self._page_state is None:
            return
        # Only append if the final page has actual content — single
        # empty-page chapters shouldn't show up in the diagnostic.
        nb = self._page_state.notebook
        slide = self._page_state.slide
        if not nb.blocks and slide.diagram_id is None:
            return
        self.report.pages.append(self._page_summary())

    # ------------------------------------------------------------------
    # Look-ahead timing precomputation
    # ------------------------------------------------------------------

    def _precompute_timings(self, fragments: list[ScriptFragment]) -> list[float]:
        """For each fragment index i, record cumulative audio_ms at the
        END of that fragment. TextFragment contributes len*WPM ms; PAUSE
        contributes its configured duration; all other fragments are 0ms.
        """
        timings: list[float] = []
        cum = 0.0
        for f in fragments:
            kind = getattr(f, "kind", None)
            if kind == "text":
                cum += len(f.text) * WPM_CHARS_PER_MS * 1000.0
            elif kind == "pause":
                # Coarse: short=250ms, long=750ms (matches config defaults).
                dur = getattr(f, "duration", "short")
                cum += 750.0 if dur == "long" else 250.0
            timings.append(cum)
        return timings

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def _handle(
        self, frag: ScriptFragment, fragments: list[ScriptFragment], idx: int
    ) -> list[ScriptFragment]:
        """Returns a list of fragments to emit. Empty list = drop;
        multi-element = synthetic injection (e.g., PageBreakFragment before
        the triggering fragment)."""
        kind = frag.kind

        if kind == "text":
            return [self._handle_text(frag)]  # type: ignore[arg-type]
        if kind == "show_diagram":
            return await self._handle_show_diagram(frag, fragments, idx)  # type: ignore[arg-type]
        if kind == "clear_annotations":
            r = self._handle_clear(frag)  # type: ignore[arg-type]
            return [r] if r is not None else []
        if kind in NOTEBOOK_FRAGMENT_KINDS:
            return await self._handle_notebook_block(frag, fragments, idx)
        if kind == "new_page":
            return await self._handle_new_page(frag, fragments, idx)  # type: ignore[arg-type]
        if kind == "focus":
            r = self._handle_focus(frag)  # type: ignore[arg-type]
            return [r] if r is not None else []
        if kind == "unfocus":
            r = self._handle_unfocus(frag)  # type: ignore[arg-type]
            return [r] if r is not None else []
        if kind == "trace":
            r = self._handle_trace(frag)  # type: ignore[arg-type]
            return [r] if r is not None else []
        if kind == "mark_point":
            r = self._handle_mark_point(frag)  # type: ignore[arg-type]
            return [r] if r is not None else []
        if kind == "point_at":
            r = self._handle_point_at(frag)  # type: ignore[arg-type]
            return [r] if r is not None else []
        if kind == "write_margin":
            r = self._handle_write_margin(frag)  # type: ignore[arg-type]
            return [r] if r is not None else []
        if kind in ("pin", "callout", "bracket", "highlight", "pulse"):
            self._handle_legacy_annotation(kind)
            return []

        # All other fragments pass through unchanged (pause, strike, etc.).
        return [frag]

    # ------------------------------------------------------------------
    # Page summary helper
    # ------------------------------------------------------------------

    def _page_summary(self) -> PageSummary:
        assert self._page_state is not None
        nb = self._page_state.notebook
        slide = self._page_state.slide
        return PageSummary(
            page_index=self._page_state.page_index,
            topic_id=self._page_state.topic_id,
            slide_diagram_id=slide.diagram_id,
            notebook_block_count=len(nb.blocks),
            notebook_height_used_px=float(nb.height_used),
            notebook_height_total_px=float(nb.total_height),
            annotations_count=slide.annotations_count,
        )

    def _audio_time_at(self, idx: int) -> float:
        if 0 <= idx < len(self._fragment_timings):
            return self._fragment_timings[idx]
        return float(self._cumulative_audio_ms)

    def _ensure_page_state(self) -> None:
        if self._layout is None or self._page_state is not None:
            return
        self._page_state = self._layout.initial_page_state(topic_id=self._topic_id)

    # ------------------------------------------------------------------
    # Non-annotation handlers
    # ------------------------------------------------------------------

    def _handle_text(self, frag: TextFragment) -> TextFragment:
        # Estimate cumulative audio time. Off by a constant factor — fine
        # for relative-time comparisons (layout look-ahead).
        self._cumulative_audio_ms += int(len(frag.text) * WPM_CHARS_PER_MS * 1000)
        return frag

    async def _handle_show_diagram(
        self,
        frag: DiagramFragment,
        fragments: list[ScriptFragment],
        idx: int,
    ) -> list[ScriptFragment]:
        # Doc-18 path: build the focus state. If layout is off, this is the
        # entire handler — early return.
        new_state = self._build_diagram_state(frag.diagram_id)
        if new_state is None:
            logger.info(
                "ShowDiagram for unknown id %s — composer will drop all "
                "downstream focus until next ShowDiagram",
                frag.diagram_id,
            )
        # Stamp the diagram's presentation_mode onto the fragment so the
        # frontend can choose build-up vs overview rendering. Tolerate
        # missing Diagram or missing field — defaults to None.
        diagram_obj = self._diagrams_by_id.get(frag.diagram_id)
        if diagram_obj is not None:
            mode = getattr(diagram_obj, "presentation_mode", None)
            if mode in ("build_up", "overview"):
                frag.presentation_mode = mode
        if self._layout is None:
            self._active = new_state
            return [frag]

        # Phase 3: try to place the diagram on the current page.
        self._ensure_page_state()
        assert self._page_state is not None  # ensured above
        diagram = self._diagrams_by_id.get(frag.diagram_id)

        placement, slide_element_bounds, was_break = await self._layout.place_diagram(
            frag, diagram, self._page_state
        )

        if not was_break:
            # Fits on current page (either same id, no prior diagram, or
            # first diagram of the page).
            self._active = new_state
            self._stamp_diagram_placement(frag, placement, slide_element_bounds)
            return [frag]

        # Need to break: a different diagram is already on this page.
        # Look-ahead decision is "new_diagram" → always swap to this new id.
        slide_action, _next = self._layout.decide_slide_action(
            fragments,
            self._fragment_timings,
            idx,
            self._page_state,
            trigger_reason="new_diagram",
        )
        # decide_slide_action returns next_diagram_id from look-ahead, but
        # for new_diagram trigger we know it's THIS fragment's id. Override.
        carry_ids = self._layout.select_carry_forward_ids(self._page_state)
        self.report.pages.append(self._page_summary())
        break_frag = PageBreakFragment(
            kind="page_break",
            new_page_index=self._page_state.page_index + 1,
            slide_action="swap",
            next_diagram_id=frag.diagram_id,
            notebook_carry_forward_ids=carry_ids,
            reason="new_diagram",
        )
        self.report.record_break("new_diagram")
        self._page_state = self._layout.open_new_page(
            self._page_state,
            "swap",
            frag.diagram_id,
            audio_time_ms=self._audio_time_at(idx),
        )

        # Retry placement on the fresh page (slide is empty now).
        placement, slide_element_bounds, _ = await self._layout.place_diagram(
            frag, diagram, self._page_state
        )
        self._active = new_state
        self._stamp_diagram_placement(frag, placement, slide_element_bounds)
        return [break_frag, frag]

    @staticmethod
    def _stamp_diagram_placement(
        frag: DiagramFragment, placement, slide_element_bounds
    ) -> None:
        if placement is not None:
            frag.placement = placement  # type: ignore[attr-defined]
        if slide_element_bounds:
            frag.slide_element_bounds = slide_element_bounds  # type: ignore[attr-defined]

    def _build_diagram_state(self, diagram_id: str) -> _PerDiagramState | None:
        diagram = self._diagrams_by_id.get(diagram_id)
        if diagram is None:
            return None
        render_data = getattr(diagram, "render_data", None)
        if not isinstance(render_data, dict):
            return None
        dictionary = render_data.get("dictionary")
        if not isinstance(dictionary, dict) or not dictionary:
            # Phase-1 legacy: warn but still create a state so non-focus
            # fragments flow. All role lookups will miss → focus drops.
            logger.info(
                "Diagram %s has no semantic dictionary — focus targeting it will drop",
                diagram_id,
            )
            return _PerDiagramState(diagram_id=diagram_id, dictionary={})

        return _PerDiagramState(diagram_id=diagram_id, dictionary=dictionary)

    def _handle_clear(
        self, frag: ClearAnnotationsFragment
    ) -> ClearAnnotationsFragment | None:
        """Handle RESET_FOCUS (and back-compat CLEAR_ANNOTATIONS).

        Wipes focus state for the active diagram. Emits a
        ClearAnnotationsFragment so the frontend can clear any residual
        focus visual.
        """
        if self._active is None:
            self.report.record_drop("clear_no_active_diagram")
            logger.warning("RESET_FOCUS before any SHOW_DIAGRAM — dropping")
            return None
        self._active.focus_role = None
        frag.diagram_id = self._active.diagram_id
        self.report.record_emit()
        # Reset per-page annotation count for diagnostics symmetry.
        if self._page_state is not None:
            self._page_state.slide.annotations_count = 0
        return frag

    async def _handle_notebook_block(
        self,
        frag: ScriptFragment,
        fragments: list[ScriptFragment],
        idx: int,
    ) -> list[ScriptFragment]:
        """Place a notebook block. If overflow → inject PageBreak + retry."""
        if self._layout is None:
            # Phase 2 mode: pass through unmodified.
            return [frag]

        self._ensure_page_state()
        assert self._page_state is not None
        placement, was_break = await self._layout.place_text(frag, self._page_state)
        if not was_break:
            self._stamp_placement(frag, placement)
            return [frag]

        # Overflow: decide slide action via look-ahead, close current page,
        # open new page, retry.
        slide_action, next_diagram_id = self._layout.decide_slide_action(
            fragments,
            self._fragment_timings,
            idx,
            self._page_state,
            trigger_reason="text_overflow",
        )
        carry_ids = self._layout.select_carry_forward_ids(self._page_state)
        self.report.pages.append(self._page_summary())
        break_frag = PageBreakFragment(
            kind="page_break",
            new_page_index=self._page_state.page_index + 1,
            slide_action=slide_action,  # type: ignore[arg-type]
            next_diagram_id=next_diagram_id,
            notebook_carry_forward_ids=carry_ids,
            reason="text_overflow",
        )
        self.report.record_break("text_overflow")
        self._page_state = self._layout.open_new_page(
            self._page_state,
            slide_action,
            next_diagram_id,
            audio_time_ms=self._audio_time_at(idx),
        )
        # Retry on the new page. If it STILL overflows (single block taller
        # than a page), place it anyway with measured=False.
        placement, was_break = await self._layout.place_text(frag, self._page_state)
        if was_break:
            logger.warning(
                "place_text: block too tall for a single page; placing without measurement",
                extra={"fragment_id": getattr(frag, "id", "")},
            )
            placement = None  # fall back; frontend renders via flow
        self._stamp_placement(frag, placement)
        return [break_frag, frag]

    @staticmethod
    def _stamp_placement(frag: ScriptFragment, placement) -> None:
        if placement is None:
            return
        # All 6 notebook fragments accept a `placement` attribute (added
        # in chunker.py via Phase 3 schema extension).
        if isinstance(
            frag,
            (
                SectionFragment,
                EquationFragment,
                StepFragment,
                KeyPointFragment,
                TextEntryFragment,
                AnswerFragment,
            ),
        ):
            frag.placement = placement  # type: ignore[assignment]

    async def _handle_new_page(
        self,
        frag: NewPageFragment,
        fragments: list[ScriptFragment],
        idx: int,
    ) -> list[ScriptFragment]:
        """Writer-marker `<<NEW_PAGE>>` → emit a PageBreakFragment."""
        if self._layout is None or self._page_state is None:
            # Pass through as a legacy NewPageFragment when layout is off
            # (downstream _render_fragments maps it to NewPageEvent).
            return [frag]

        slide_action, next_diagram_id = self._layout.decide_slide_action(
            fragments,
            self._fragment_timings,
            idx,
            self._page_state,
            trigger_reason="writer_marker",
        )
        carry_ids = (
            list(frag.carry_forward_ids)
            if frag.carry_forward_ids
            else self._layout.select_carry_forward_ids(self._page_state)
        )
        self.report.pages.append(self._page_summary())
        break_frag = PageBreakFragment(
            kind="page_break",
            new_page_index=self._page_state.page_index + 1,
            slide_action=slide_action,  # type: ignore[arg-type]
            next_diagram_id=next_diagram_id,
            notebook_carry_forward_ids=carry_ids,
            reason="writer_marker",
        )
        self.report.record_break("writer_marker")
        self._page_state = self._layout.open_new_page(
            self._page_state,
            slide_action,
            next_diagram_id,
            audio_time_ms=self._audio_time_at(idx),
        )
        return [break_frag]

    # ------------------------------------------------------------------
    # Attention-direction handlers (doc 18 spotlight)
    # ------------------------------------------------------------------

    def _bump_annotations(self) -> None:
        if self._page_state is not None:
            self._page_state.slide.annotations_count += 1

    def _handle_focus(self, frag: FocusFragment) -> ScriptFragment | None:
        """Validate FOCUS against active diagram; stamp diagram_id; emit.

        Drops when:
          - no active diagram
          - role not in the active diagram's dictionary
        Re-FOCUS on the same role is allowed (re-emit; frontend can repaint
        as a brief re-attention flash). Empty inline label is fine.
        """
        if self._active is None:
            self.report.record_drop("no_active_diagram")
            return None
        role = frag.role.strip()
        if not role:
            self.report.record_drop("focus_empty_role")
            return None
        if not self._active.has_role(role):
            self.report.record_drop("role_unknown")
            return None
        resolved_id = self._active.role_to_element_id(role)
        frag.role = role
        frag.diagram_id = self._active.diagram_id
        # Doc 19 §A-3: stamp the stable element_id so the audio_pipeline can
        # populate FocusEvent.target_element_id (the preferred selector).
        frag.element_id = resolved_id or ""
        self._active.focus_role = role
        self.report.record_emit()
        self._bump_annotations()
        return frag

    def _handle_unfocus(self, frag: UnfocusFragment) -> ScriptFragment | None:
        """Clear the current focus. Drops when nothing is focused (no-op)."""
        if self._active is None:
            self.report.record_drop("no_active_diagram")
            return None
        if self._active.focus_role is None:
            # No-op; not worth emitting an event.
            self.report.record_drop("unfocus_no_focus")
            return None
        self._active.focus_role = None
        frag.diagram_id = self._active.diagram_id
        self.report.record_emit()
        return frag

    # ------------------------------------------------------------------
    # New live-annotation handlers (doc 19 §12)
    # ------------------------------------------------------------------

    def _handle_trace(self, frag: TraceFragment) -> ScriptFragment | None:
        """Trace an element's stroke. Drops if no active diagram or unknown id."""
        if self._active is None:
            self.report.record_drop("no_active_diagram")
            return None
        element_id = frag.element_id.strip()
        if not element_id:
            self.report.record_drop("trace_empty_element_id")
            return None
        if not self._active.has_element_id(element_id):
            self.report.record_drop("element_id_unknown")
            return None
        frag.element_id = element_id
        frag.diagram_id = self._active.diagram_id
        self.report.record_emit()
        self._bump_annotations()
        return frag

    def _handle_mark_point(self, frag: MarkPointFragment) -> ScriptFragment | None:
        """Drop a marker at (x, y). Drops only when no active diagram —
        MARK_POINT carries raw coordinates and doesn't validate against the
        dictionary.
        """
        if self._active is None:
            self.report.record_drop("no_active_diagram")
            return None
        frag.diagram_id = self._active.diagram_id
        self.report.record_emit()
        self._bump_annotations()
        return frag

    def _handle_point_at(self, frag: PointAtFragment) -> ScriptFragment | None:
        """Point at an element. Drops on unknown element_id."""
        if self._active is None:
            self.report.record_drop("no_active_diagram")
            return None
        element_id = frag.element_id.strip()
        if not element_id:
            self.report.record_drop("point_at_empty_element_id")
            return None
        if not self._active.has_element_id(element_id):
            self.report.record_drop("element_id_unknown")
            return None
        frag.element_id = element_id
        frag.diagram_id = self._active.diagram_id
        self.report.record_emit()
        self._bump_annotations()
        return frag

    def _handle_write_margin(self, frag: WriteMarginFragment) -> ScriptFragment | None:
        """Margin note anchored to an element. Drops on unknown anchor."""
        if self._active is None:
            self.report.record_drop("no_active_diagram")
            return None
        anchor = frag.anchor_element_id.strip()
        if not anchor:
            self.report.record_drop("write_margin_empty_anchor")
            return None
        if not self._active.has_element_id(anchor):
            self.report.record_drop("element_id_unknown")
            return None
        if not frag.text.strip():
            self.report.record_drop("write_margin_empty_text")
            return None
        frag.anchor_element_id = anchor
        frag.diagram_id = self._active.diagram_id
        self.report.record_emit()
        self._bump_annotations()
        return frag

    def _handle_legacy_annotation(self, kind: str) -> None:
        """Drop legacy PIN/CALLOUT/BRACKET/HIGHLIGHT/PULSE fragments.

        Counts them under `drops_by_reason["legacy_annotation_deprecated"]`.
        Logs once per walker lifetime to avoid spamming during transition.
        """
        if not self._legacy_warned:
            logger.warning(
                "Encountered legacy annotation markers (%s, ...); these are "
                "deprecated in favor of <<FOCUS:role>> and are being dropped. "
                "Re-ingest with the updated narration prompt to use spotlight.",
                kind,
            )
            self._legacy_warned = True
        self.report.record_drop("legacy_annotation_deprecated")
