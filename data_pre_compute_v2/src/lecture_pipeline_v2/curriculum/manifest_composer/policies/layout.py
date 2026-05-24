"""LayoutPlanner — Phase 3 measured layout + page-break decisions.

Owns three responsibilities:
  1. Measure every notebook block via the MeasurementService.
  2. Track per-page state (notebook cursor, slide diagram, occupancy).
  3. Decide page-break triggers + slide_action (keep/swap/release) using
     a forward look-ahead window over the fragment stream.

The Walker drives this — calls place_text / place_diagram per fragment,
handles the was_break signal by injecting a PageBreakFragment and opening
a new page, and uses decide_slide_action when a break fires.

All page-coordinate math is in pixel space (page_index + Rect in viewport
coords). Diagram placement converts viewBox units → page coords using the
diagram's intrinsic viewBox and the slide region's "contain" scale.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from lecture_pipeline_v2.config import LayoutConfig
from lecture_pipeline_v2.curriculum.manifest_composer import geometry as geo
from lecture_pipeline_v2.curriculum.manifest_composer.measurement import (
    MeasurementService,
)
from lecture_pipeline_v2.curriculum.models import Placement, Rect as PydRect

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Page-state dataclasses
# ---------------------------------------------------------------------------


@dataclass
class BlockPlacement:
    """One placed notebook block on a page."""

    fragment_id: str
    block_type: str
    rect: geo.Rect  # page-coord pixels
    measured: bool = True


@dataclass
class NotebookState:
    blocks: list[BlockPlacement] = field(default_factory=list)
    cursor_y: float = 0.0
    inner_top: float = 0.0
    inner_bottom: float = 0.0  # the y past which a block overflows
    inner_x: float = 0.0
    inner_width: float = 0.0

    @property
    def total_height(self) -> float:
        return self.inner_bottom - self.inner_top

    @property
    def height_used(self) -> float:
        return max(0.0, self.cursor_y - self.inner_top)


@dataclass
class SlideState:
    diagram_id: str | None = None
    placed_rect: geo.Rect | None = None
    element_bounds: dict[str, geo.Rect] = field(default_factory=dict)
    annotations_count: int = 0


@dataclass
class PageState:
    page_index: int
    slide: SlideState
    notebook: NotebookState
    audio_time_ms: float = 0.0
    topic_id: str = ""


# ---------------------------------------------------------------------------
# Fragment introspection helpers (duck-typed to keep us decoupled from
# chunker's exact dataclass shapes)
# ---------------------------------------------------------------------------


_KIND_TO_BLOCK_TYPE: dict[str, str] = {
    "section": "SECTION",
    "equation": "EQUATION",
    "step": "STEP",
    "key_point": "KEY",
    "text_entry": "TEXT",
    "answer": "ANSWER",
}

NOTEBOOK_FRAGMENT_KINDS = frozenset(_KIND_TO_BLOCK_TYPE.keys())


def _frag_kind(frag: Any) -> str:
    return getattr(frag, "kind", "") or ""


def _frag_to_block_type(frag: Any) -> str:
    kind = _frag_kind(frag)
    if kind not in _KIND_TO_BLOCK_TYPE:
        raise ValueError(f"Cannot map fragment kind {kind!r} to block_type")
    return _KIND_TO_BLOCK_TYPE[kind]


def _frag_content(frag: Any) -> str:
    kind = _frag_kind(frag)
    if kind == "section":
        return getattr(frag, "title", "") or ""
    if kind == "equation":
        return getattr(frag, "latex", "") or ""
    return getattr(frag, "text", "") or ""


def _frag_attrs(frag: Any) -> dict[str, Any]:
    kind = _frag_kind(frag)
    if kind == "step":
        indent = int(getattr(frag, "indent", 0) or 0)
        return {"indent": indent} if indent > 0 else {}
    return {}


def _frag_id(frag: Any) -> str:
    return getattr(frag, "id", "") or ""


def _to_pyd_rect(r: geo.Rect) -> PydRect:
    """Convert dataclass Rect → Pydantic Rect for event serialization."""
    return PydRect(x=r.x, y=r.y, width=r.width, height=r.height)


# ---------------------------------------------------------------------------
# LayoutPlanner
# ---------------------------------------------------------------------------


class LayoutPlanner:
    """Measure + place notebook blocks, scale diagrams, decide slide actions."""

    def __init__(
        self, layout_config: LayoutConfig, measurement: MeasurementService
    ) -> None:
        self._cfg = layout_config
        self._measurement = measurement

    # ──────────── page state lifecycle ────────────

    def initial_page_state(self, topic_id: str = "") -> PageState:
        nb = self._cfg.notebook
        inner_top = float(nb.y + nb.padding)
        inner_bottom = float(nb.y + nb.height - nb.padding)
        inner_x = float(nb.x + nb.padding)
        inner_width = float(nb.width - 2 * nb.padding)
        return PageState(
            page_index=0,
            slide=SlideState(),
            notebook=NotebookState(
                blocks=[],
                cursor_y=inner_top,
                inner_top=inner_top,
                inner_bottom=inner_bottom,
                inner_x=inner_x,
                inner_width=inner_width,
            ),
            audio_time_ms=0.0,
            topic_id=topic_id,
        )

    def open_new_page(
        self,
        prev: PageState,
        slide_action: str,
        next_diagram_id: str | None,
        audio_time_ms: float,
        topic_id: str | None = None,
    ) -> PageState:
        """Build the PageState after a page break. `slide_action` determines
        what carries forward on the slide side; the notebook always resets.
        """
        nb = self._cfg.notebook
        inner_top = float(nb.y + nb.padding)
        inner_bottom = float(nb.y + nb.height - nb.padding)
        inner_x = float(nb.x + nb.padding)
        inner_width = float(nb.width - 2 * nb.padding)
        new_slide = self._slide_for_new_page(prev.slide, slide_action)
        return PageState(
            page_index=prev.page_index + 1,
            slide=new_slide,
            notebook=NotebookState(
                blocks=[],
                cursor_y=inner_top,
                inner_top=inner_top,
                inner_bottom=inner_bottom,
                inner_x=inner_x,
                inner_width=inner_width,
            ),
            audio_time_ms=audio_time_ms,
            topic_id=topic_id if topic_id is not None else prev.topic_id,
        )

    def _slide_for_new_page(
        self, prev_slide: SlideState, slide_action: str
    ) -> SlideState:
        if slide_action == "keep":
            # Diagram, placement, and element_bounds carry forward.
            # Annotations are page-scoped — reset count.
            return SlideState(
                diagram_id=prev_slide.diagram_id,
                placed_rect=prev_slide.placed_rect,
                element_bounds=dict(prev_slide.element_bounds),
                annotations_count=0,
            )
        # "swap" and "release" both leave the slide blank initially —
        # for "swap" the next ShowDiagramFragment will populate it.
        return SlideState()

    # ──────────── place a text/notebook fragment ────────────

    async def place_text(
        self,
        frag: Any,
        page_state: PageState,
    ) -> tuple[Placement | None, bool]:
        """Measure block and try to place it on `page_state.notebook`.

        Returns (placement, was_break):
          - was_break=False: placement is the resolved Placement; the page
            state has been mutated to include this block.
          - was_break=True: placement is None; the block does NOT fit on the
            current page. Caller should open a new page and retry.
        """
        block_type = _frag_to_block_type(frag)
        content = _frag_content(frag)
        attrs = _frag_attrs(frag)
        width = float(self._cfg.block_default_widths.get(block_type, 540))

        try:
            dims = await self._measurement.measure(block_type, content, attrs, width)
        except Exception as e:
            # Measurement failure — fall back to a coarse estimate.
            # Better to place imprecisely than to abort the chapter.
            logger.warning(
                "place_text: measurement failed, using estimate",
                extra={"block_type": block_type, "error": str(e)},
            )
            dims = {
                "width": width,
                "height": self._estimate_height(block_type, content),
            }
            measured = False
        else:
            measured = True

        height = float(dims["height"])
        nb = page_state.notebook
        safety = self._cfg.pagination.overflow_safety_margin_px
        if nb.cursor_y + height > nb.inner_bottom - safety:
            return None, True

        rect = geo.Rect(
            x=nb.inner_x, y=nb.cursor_y, width=float(dims["width"]), height=height
        )
        placement = Placement(
            page_index=page_state.page_index,
            rect=_to_pyd_rect(rect),
            measured=measured,
        )
        nb.blocks.append(
            BlockPlacement(
                fragment_id=_frag_id(frag),
                block_type=block_type,
                rect=rect,
                measured=measured,
            )
        )
        nb.cursor_y = rect.y + height + self._cfg.block_spacing_px
        return placement, False

    def _estimate_height(self, block_type: str, content: str) -> float:
        """Coarse height fallback if measurement fails. Counts character
        wrap at the configured default width with rough char-width.
        """
        approx_char_width = 8.0  # pixels at body font
        line_height = 24.0
        width = float(self._cfg.block_default_widths.get(block_type, 540))
        chars_per_line = max(1, int(width / approx_char_width))
        lines = max(1, (len(content) + chars_per_line - 1) // chars_per_line)
        return line_height * lines + 8.0  # +padding fudge

    # ──────────── place a diagram fragment ────────────

    async def place_diagram(
        self,
        frag: Any,
        diagram: Any | None,
        page_state: PageState,
    ) -> tuple[Placement | None, dict[str, PydRect] | None, bool]:
        """Compute the slide rect and per-role page-coord bounds for a diagram.

        Returns (placement, slide_element_bounds, was_break):
          - was_break=True if the page already shows a DIFFERENT diagram_id.
            Caller opens a new page (with slide_action="swap") and retries.
          - If diagram is None or has no render_data, falls back to a
            slide_inner-sized rect with measured=False, no bounds.
        """
        new_diagram_id = getattr(frag, "diagram_id", "") or ""
        slide = page_state.slide
        if slide.diagram_id is not None and slide.diagram_id != new_diagram_id:
            return None, None, True

        slide_cfg = self._cfg.slide
        inner_x = float(slide_cfg.x + slide_cfg.padding)
        inner_y = float(slide_cfg.y + slide_cfg.padding)
        inner_w = float(slide_cfg.width - 2 * slide_cfg.padding)
        inner_h = float(slide_cfg.height - 2 * slide_cfg.padding)

        view_box = self._extract_view_box(diagram)
        if view_box is None:
            # Unknown viewBox — place at full inner with measured=False.
            placed = geo.Rect(x=inner_x, y=inner_y, width=inner_w, height=inner_h)
            placement = Placement(
                page_index=page_state.page_index,
                rect=_to_pyd_rect(placed),
                measured=False,
            )
            page_state.slide = SlideState(
                diagram_id=new_diagram_id,
                placed_rect=placed,
                element_bounds={},
                annotations_count=0,
            )
            return placement, {}, False

        vbx, vby, vbw, vbh = view_box
        scale = min(inner_w / vbw, inner_h / vbh, float(self._cfg.diagram.max_scale))
        scaled_w = vbw * scale
        scaled_h = vbh * scale
        # Center in slide inner region.
        placed_x = inner_x + (inner_w - scaled_w) / 2
        placed_y = inner_y + (inner_h - scaled_h) / 2
        placed_rect = geo.Rect(x=placed_x, y=placed_y, width=scaled_w, height=scaled_h)

        # Per-role page-coord bounds. Skip entries with malformed bounds.
        dictionary = (getattr(diagram, "render_data", {}) or {}).get("dictionary", {})
        page_bounds_dc: dict[str, geo.Rect] = {}
        for el_id, entry in dictionary.items():
            if not isinstance(entry, dict):
                continue
            role = entry.get("role")
            bounds = entry.get("bounds")
            if not role or not bounds or len(bounds) < 4:
                continue
            try:
                bx, by, bw, bh = (
                    float(bounds[0]),
                    float(bounds[1]),
                    float(bounds[2]),
                    float(bounds[3]),
                )
            except (TypeError, ValueError):
                continue
            page_bounds_dc[role] = geo.Rect(
                x=placed_x + (bx - vbx) * scale,
                y=placed_y + (by - vby) * scale,
                width=bw * scale,
                height=bh * scale,
            )

        page_state.slide = SlideState(
            diagram_id=new_diagram_id,
            placed_rect=placed_rect,
            element_bounds=page_bounds_dc,
            annotations_count=0,
        )
        placement = Placement(
            page_index=page_state.page_index,
            rect=_to_pyd_rect(placed_rect),
            measured=True,
        )
        # Convert page_bounds to Pydantic Rects for the outgoing event.
        page_bounds_pyd = {role: _to_pyd_rect(r) for role, r in page_bounds_dc.items()}
        return placement, page_bounds_pyd, False

    def _extract_view_box(
        self, diagram: Any
    ) -> tuple[float, float, float, float] | None:
        render = (
            (getattr(diagram, "render_data", None) or {}) if diagram is not None else {}
        )
        vb = render.get("viewBox") or render.get("view_box")
        if isinstance(vb, str):
            parts = vb.split()
            if len(parts) == 4:
                try:
                    return tuple(float(p) for p in parts)  # type: ignore[return-value]
                except ValueError:
                    return None
        if isinstance(vb, (list, tuple)) and len(vb) == 4:
            try:
                return (float(vb[0]), float(vb[1]), float(vb[2]), float(vb[3]))
            except (TypeError, ValueError):
                return None
        return None

    # ──────────── slide-action decision (look-ahead) ────────────

    def decide_slide_action(
        self,
        fragments: list[Any],
        fragment_timings_ms: list[float],
        current_idx: int,
        page_state: PageState,
        trigger_reason: str,
    ) -> tuple[str, str | None]:
        """Apply the §7.5 decision rules using look-ahead.

        Walks forward from current_idx+1 up to lookahead_seconds of audio
        time, collecting:
          - the first ShowDiagram fragment (sets next_diagram_id)
          - any reference fragments (PIN/CALLOUT/HIGHLIGHT/PULSE/BRACKET)
            whose role is in the current diagram's dictionary.

        Returns (slide_action, next_diagram_id).
        """
        window_ms = self._cfg.pagination.lookahead_seconds * 1000.0
        base_time = (
            fragment_timings_ms[current_idx]
            if 0 <= current_idx < len(fragment_timings_ms)
            else 0.0
        )

        current_roles = set(page_state.slide.element_bounds.keys())
        next_diagram_id: str | None = None
        references_in_current = False

        for j in range(current_idx + 1, len(fragments)):
            t = fragment_timings_ms[j] if j < len(fragment_timings_ms) else base_time
            if t - base_time > window_ms:
                break
            f = fragments[j]
            kind = _frag_kind(f)
            if kind == "show_diagram":
                next_diagram_id = getattr(f, "diagram_id", None)
                break  # everything past a new diagram is "next slide's problem"
            if kind in ("pin", "callout", "highlight", "pulse"):
                if getattr(f, "role", None) in current_roles:
                    references_in_current = True
            elif kind == "bracket":
                ra = getattr(f, "role_a", None)
                rb = getattr(f, "role_b", None)
                if (ra and ra in current_roles) or (rb and rb in current_roles):
                    references_in_current = True

        if trigger_reason == "new_diagram":
            return "swap", next_diagram_id

        if trigger_reason == "text_overflow":
            if references_in_current or next_diagram_id is None:
                return "keep", None
            return "release", None

        if trigger_reason == "writer_marker":
            if next_diagram_id is not None:
                return "swap", next_diagram_id
            return "keep", None

        # Unknown reason — safest default.
        return "keep", None

    # ──────────── carry-forward auto-selection ────────────

    def select_carry_forward_ids(self, page_state: PageState) -> list[str]:
        """Pick block IDs to carry to the next page.

        Auto-select rule: the most-recently-placed ANSWER or KEY block, if
        not preceded (going backwards) by a SECTION boundary. SECTION acts
        as a "fresh context starts here" marker that shouldn't carry past
        a page break.
        """
        for block in reversed(page_state.notebook.blocks):
            if block.block_type in ("ANSWER", "KEY"):
                return [block.fragment_id] if block.fragment_id else []
            if block.block_type == "SECTION":
                break
        return []
