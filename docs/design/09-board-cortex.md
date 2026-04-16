# 09 — Board Cortex: Giving the Teaching Agent Eyes

## Problem Statement

The teaching agent's board intelligence is fundamentally broken despite 9 phases of prior work.

**What we built** (Phases 1-9 of design doc 06): BoardState element tracking, SceneGraph pixel-precise spatial model, BoardGraph semantic clusters, 5 named layout patterns, zone placement instructions, concept grouping, infinite canvas, anticipation caching.

**What the LLM actually receives**:

```
Cluster: Free body diagram [anchor: design-1] (Newton's Laws)
  design-1 (Free body diagram) — center-left
    ├── eq-2 (F = ma) ──illustrates── center-right
    └── text-1 (Key insight) ──supports── top-center

Free zones: top-left, top-right, bottom-left, bottom-center, bottom-right
```

That's a **flat text list with zone labels**. The LLM reads "Free zones: top-right, bottom-left" and picks one. This is a blind person being told "there's space on your right." It's not vision. It's not spatial reasoning. It's a dropdown menu.

**The root cause**: We're asking the LLM to make geometric decisions it's constitutionally incapable of making. Research consistently shows LLMs degrade 42-80% on spatial tasks as complexity grows (IJCAI 2025 Survey). The LLM has zero ability to reason about:

- Whether the new element will visually crowd existing content
- What the overall visual "feel" of the board is
- Whether there's a logical reading flow
- How big the new thing will be before it's rendered
- Where precisely to place something relative to another element

**The solution**: Split the brain. LLM handles "what goes on the board and why" (pedagogy). A deterministic spatial solver handles "where exactly, will it fit, how does it relate" (geometry). Each does what it's good at.

---

## Architecture: The Board Cortex

The Board Cortex is a perceptual and spatial computation layer between the teaching agent (LLM) and the board. It gives the agent "eyes."

```
┌───────────────────────────────────────────────────────────┐
│  Teaching Agent (LLM)                                     │
│  Sees: ASCII board snapshot + placement suggestions       │
│  Outputs: PlacementIntent (near="design-1", relation=     │
│           "right_of", size="medium")                      │
└────────────────────────┬──────────────────────────────────┘
                         │ semantic intent
                         ▼
┌───────────────────────────────────────────────────────────┐
│  Board Cortex                                             │
│  ┌─────────────┐  ┌──────────┐  ┌──────────────────────┐ │
│  │ Spatial      │  │ Size     │  │ Scenario Planner     │ │
│  │ Solver       │  │ Estimator│  │ (teaching patterns)  │ │
│  │ (MaxRects)   │  │          │  │                      │ │
│  └──────┬──────┘  └────┬─────┘  └──────────┬───────────┘ │
│         │              │                    │             │
│  ┌──────▼──────────────▼────────────────────▼───────────┐ │
│  │ Placement Executor                                   │ │
│  │ intent + size estimate + free space → exact (x, y)   │ │
│  └──────────────────────┬───────────────────────────────┘ │
│                         │                                 │
│  ┌──────────────────────▼───────────────────────────────┐ │
│  │ ASCII Snapshot Generator                             │ │
│  │ board state → 2D visual text + suggestions           │ │
│  └──────────────────────────────────────────────────────┘ │
└────────────────────────┬──────────────────────────────────┘
                         │ exact coordinates
                         ▼
┌───────────────────────────────────────────────────────────┐
│  Frontend                                                 │
│  Renders at exact position → reports actual bounds back   │
└───────────────────────────────────────────────────────────┘
```

### The Flow (Before vs After)

**Before (current)**:
```
LLM thinks → picks zone="center-right" → frontend auto-arranges → hope for the best
```

**After (Board Cortex)**:
```
LLM sees ASCII snapshot → says near="design-1", relation="right_of"
  → Solver checks: space right of design-1? 400x300px free. Equation ~280x80px. Fits.
  → Exact position: (1020, 350)
  → Frontend renders at (1020, 350)
  → Frontend reports actual bounds
  → Solver updates free space map
  → Next turn: LLM sees updated ASCII snapshot with new suggestions
```

---

## Research Basis

| Component | Research | Key Finding |
|-----------|----------|-------------|
| MaxRects solver | Game engine texture packing (standard) | Sub-millisecond free space detection, proven at scale |
| ASCII 2D representation | Cartesian JSON + spatial descriptions (U. Illinois 2025) | LLMs reason significantly better with 2D text vs flat lists |
| Neural-symbolic split | LaySPA (Sep 2025), VADAR (CVPR 2025) | LLM for semantics + solver for geometry = best of both |
| Constraint satisfaction | RoomPlanner, 3D-Layout-R1 | 93%+ constraint satisfaction within 5 iterations |
| Size-aware placement | LaySPA hybrid reward | Boundary adherence + non-overlap + size consistency critical |
| Visual verification | RRVF 2025 | VLM verification >> VLM generation (fast, reliable) |
| LLM spatial limits | IJCAI 2025 Survey | 42-80% degradation as spatial complexity increases |

---

## Key Files

| File | Role |
|------|------|
| `backend/src/feynman/agent/board_state.py` | BoardState, BoardElement, element tracking |
| `backend/src/feynman/agent/board.py` | BoardManager, multi-board orchestration |
| `backend/src/feynman/agent/scene_graph.py` | SceneGraph, pixel-precise spatial model |
| `backend/src/feynman/agent/board_graph.py` | BoardGraph, semantic relationships |
| `backend/src/feynman/agent/tools.py` | All LLM function tools, `_publish_visual` |
| `backend/src/feynman/agent/prompts.py` | `build_teaching_prompt`, zone/relationship instructions |
| `backend/src/feynman/agent/teaching_context.py` | TeachingContext, wraps boards + state |
| `backend/src/feynman/visuals/schemas.py` | `_BaseInstruction`, `BoardZone`, all instruction types |
| `frontend/src/engine/whiteboard/zone-layout.ts` | Zone grid computation, element placement |
| `frontend/src/engine/whiteboard/WhiteboardScene.tsx` | Board rendering, zone-based element grouping |
| `frontend/src/engine/whiteboard/BoundsReporter.tsx` | Frontend → backend bounds feedback |
| `frontend/src/engine/whiteboard/types.ts` | `Rect`, `BoardLayout`, `PlacedElement` |

---

## Phase 1: Spatial Solver + Size Estimator

**Goal**: Pure geometry engine that knows what's on the board, how much space is free, and how big new things will be. No LLM changes. Foundation for everything.

### 1.1 Spatial Solver

New file: `backend/src/feynman/agent/spatial_solver.py`

The solver maintains a free space map using the MaxRects algorithm. Updated on every bounds report from the frontend. Queried before every placement.

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


@dataclass(frozen=True)
class Rect:
    """Axis-aligned rectangle in board space (1920x1080)."""
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2

    @property
    def area(self) -> float:
        return self.width * self.height

    def overlaps(self, other: Rect) -> bool:
        return (
            self.x < other.right and self.right > other.x
            and self.y < other.bottom and self.bottom > other.y
        )

    def contains(self, other: Rect) -> bool:
        return (
            self.x <= other.x and self.right >= other.right
            and self.y <= other.y and self.bottom >= other.bottom
        )


class SpatialRelation(StrEnum):
    RIGHT_OF = "right_of"
    LEFT_OF = "left_of"
    BELOW = "below"
    ABOVE = "above"
    CENTERED = "centered"


@dataclass
class PlacementResult:
    """Where to put something on the board."""
    x: float
    y: float
    width: float
    height: float
    confidence: float  # 0-1, how good this placement is
    zone_hint: str = ""  # nearest zone name for backward compat
    reason: str = ""  # human-readable explanation


BOARD_WIDTH = 1920
BOARD_HEIGHT = 1080
MIN_USEFUL_SIZE = 80  # px — smaller free rects aren't useful
ELEMENT_PADDING = 40  # px — minimum gap between elements


class SpatialSolver:
    """MaxRects-based free space tracker for the board.

    Maintains occupied rectangles and computes free space.
    Updated by SceneGraph bounds reports. Queried by Placement Executor.

    All methods are synchronous and sub-millisecond.
    """

    def __init__(self, width: float = BOARD_WIDTH, height: float = BOARD_HEIGHT) -> None:
        self._width = width
        self._height = height
        self._occupied: dict[str, Rect] = {}
        # MaxRects: list of maximal free rectangles
        self._free_rects: list[Rect] = [Rect(0, 0, width, height)]

    def update_occupied(self, element_id: str, rect: Rect) -> None:
        """Add or update an occupied rectangle and recompute free space."""
        self._occupied[element_id] = rect
        self._rebuild_free_rects()

    def update_all(self, elements: dict[str, Rect]) -> None:
        """Bulk update from bounds report. Replaces all occupied rects."""
        self._occupied = dict(elements)
        self._rebuild_free_rects()

    def remove(self, element_id: str) -> None:
        """Remove an element and recompute free space."""
        self._occupied.pop(element_id, None)
        self._rebuild_free_rects()

    def clear(self) -> None:
        """Clear all occupied space."""
        self._occupied.clear()
        self._free_rects = [Rect(0, 0, self._width, self._height)]

    # ── Queries ──────────────────────────────────────────

    def can_fit(self, width: float, height: float) -> bool:
        """Can a rect of this size fit anywhere on the board?"""
        for fr in self._free_rects:
            if fr.width >= width and fr.height >= height:
                return True
        return False

    def largest_free_region(self) -> Rect | None:
        """The biggest available rectangle."""
        if not self._free_rects:
            return None
        return max(self._free_rects, key=lambda r: r.area)

    def free_space_percentage(self) -> float:
        """How much of the board is unoccupied (0-1)."""
        used = sum(r.area for r in self._occupied.values())
        return max(0, 1 - used / (self._width * self._height))

    def density_by_quadrant(self) -> dict[str, float]:
        """Fill percentage per board quadrant (0-1 each)."""
        half_w, half_h = self._width / 2, self._height / 2
        quadrants = {
            "top-left": Rect(0, 0, half_w, half_h),
            "top-right": Rect(half_w, 0, half_w, half_h),
            "bottom-left": Rect(0, half_h, half_w, half_h),
            "bottom-right": Rect(half_w, half_h, half_w, half_h),
        }
        result: dict[str, float] = {}
        for name, q in quadrants.items():
            overlap_area = 0.0
            for occ in self._occupied.values():
                ix = max(occ.x, q.x)
                iy = max(occ.y, q.y)
                iw = min(occ.right, q.right) - ix
                ih = min(occ.bottom, q.bottom) - iy
                if iw > 0 and ih > 0:
                    overlap_area += iw * ih
            result[name] = min(overlap_area / q.area, 1.0)
        return result

    def find_placement(
        self,
        width: float,
        height: float,
        *,
        anchor_id: str | None = None,
        relation: SpatialRelation = SpatialRelation.RIGHT_OF,
        padding: float = ELEMENT_PADDING,
    ) -> PlacementResult | None:
        """Find the best position for a new element.

        If anchor_id is given, tries to place relative to that element.
        Falls back to best-fit in largest free region.
        """
        padded_w = width + padding * 2
        padded_h = height + padding * 2

        # Strategy 1: Place relative to anchor
        if anchor_id and anchor_id in self._occupied:
            result = self._place_near_anchor(
                width, height, self._occupied[anchor_id], relation, padding
            )
            if result:
                return result

        # Strategy 2: Best-fit in free rects (prefer reading order: top-left)
        return self._place_best_fit(width, height, padding)

    def neighbors_of(self, element_id: str, max_distance: float = 300) -> list[str]:
        """Element IDs whose centers are within max_distance of target."""
        target = self._occupied.get(element_id)
        if not target:
            return []
        result = []
        for eid, rect in self._occupied.items():
            if eid == element_id:
                continue
            dx = rect.center_x - target.center_x
            dy = rect.center_y - target.center_y
            if (dx * dx + dy * dy) ** 0.5 <= max_distance:
                result.append(eid)
        return result

    def reading_order(self) -> list[str]:
        """Element IDs sorted by visual reading flow (L→R, T→B).

        Uses a row-detection heuristic: elements within 100px vertical
        distance are on the "same row", sorted left-to-right within rows.
        """
        if not self._occupied:
            return []
        items = sorted(self._occupied.items(), key=lambda kv: kv[1].y)
        rows: list[list[tuple[str, Rect]]] = []
        for eid, rect in items:
            if rows and abs(rect.center_y - rows[-1][0][1].center_y) < 100:
                rows[-1].append((eid, rect))
            else:
                rows.append([(eid, rect)])
        result: list[str] = []
        for row in rows:
            row.sort(key=lambda kv: kv[1].x)
            result.extend(eid for eid, _ in row)
        return result

    # ── Internals ────────────────────────────────────────

    def _place_near_anchor(
        self, w: float, h: float, anchor: Rect,
        relation: SpatialRelation, padding: float,
    ) -> PlacementResult | None:
        """Try to place adjacent to an anchor element."""
        candidates: list[tuple[float, float, str]] = []

        if relation == SpatialRelation.RIGHT_OF:
            candidates = [
                (anchor.right + padding, anchor.y, "right of anchor"),
                (anchor.right + padding, anchor.center_y - h / 2, "right, vertically centered"),
            ]
        elif relation == SpatialRelation.LEFT_OF:
            candidates = [
                (anchor.x - w - padding, anchor.y, "left of anchor"),
            ]
        elif relation == SpatialRelation.BELOW:
            candidates = [
                (anchor.x, anchor.bottom + padding, "below anchor"),
                (anchor.center_x - w / 2, anchor.bottom + padding, "below, centered"),
            ]
        elif relation == SpatialRelation.ABOVE:
            candidates = [
                (anchor.x, anchor.y - h - padding, "above anchor"),
            ]
        elif relation == SpatialRelation.CENTERED:
            candidates = [
                (anchor.center_x - w / 2, anchor.center_y - h / 2, "centered on anchor"),
            ]

        for cx, cy, reason in candidates:
            candidate = Rect(cx, cy, w, h)
            # Check: within board bounds
            if cx < 0 or cy < 0 or cx + w > self._width or cy + h > self._height:
                continue
            # Check: doesn't overlap any occupied rect (with padding)
            if self._overlaps_any(candidate, padding=padding / 2):
                continue
            return PlacementResult(
                x=cx, y=cy, width=w, height=h,
                confidence=0.9, reason=reason,
                zone_hint=self._nearest_zone(cx + w / 2, cy + h / 2),
            )
        return None

    def _place_best_fit(
        self, w: float, h: float, padding: float,
    ) -> PlacementResult | None:
        """Place in the best-fitting free rectangle (reading order bias)."""
        best: Rect | None = None
        best_score = float("inf")

        for fr in self._free_rects:
            if fr.width < w + padding or fr.height < h + padding:
                continue
            # Score: prefer smaller waste area + top-left bias
            waste = (fr.width - w) * (fr.height - h)
            position_bias = fr.y * 2 + fr.x  # top-left preference
            score = waste + position_bias * 0.1
            if score < best_score:
                best_score = score
                best = fr

        if not best:
            return None

        x = best.x + padding / 2
        y = best.y + padding / 2
        return PlacementResult(
            x=x, y=y, width=w, height=h,
            confidence=0.7, reason="best-fit free region",
            zone_hint=self._nearest_zone(x + w / 2, y + h / 2),
        )

    def _overlaps_any(self, rect: Rect, padding: float = 0) -> bool:
        """Check if rect overlaps any occupied element (with optional padding)."""
        padded = Rect(
            rect.x - padding, rect.y - padding,
            rect.width + padding * 2, rect.height + padding * 2,
        )
        return any(padded.overlaps(occ) for occ in self._occupied.values())

    def _rebuild_free_rects(self) -> None:
        """Recompute MaxRects free space from scratch.

        Standard MaxRects algorithm:
        1. Start with full board as one free rect
        2. For each occupied rect, split intersecting free rects
        3. Remove free rects contained within others
        4. Filter out too-small rects
        """
        free = [Rect(0, 0, self._width, self._height)]

        for occ in self._occupied.values():
            new_free: list[Rect] = []
            for fr in free:
                if not fr.overlaps(occ):
                    new_free.append(fr)
                    continue
                # Split: up to 4 new rects from cutting occ out of fr
                # Left remainder
                if occ.x > fr.x:
                    new_free.append(Rect(fr.x, fr.y, occ.x - fr.x, fr.height))
                # Right remainder
                if occ.right < fr.right:
                    new_free.append(Rect(occ.right, fr.y, fr.right - occ.right, fr.height))
                # Top remainder
                if occ.y > fr.y:
                    new_free.append(Rect(fr.x, fr.y, fr.width, occ.y - fr.y))
                # Bottom remainder
                if occ.bottom < fr.bottom:
                    new_free.append(Rect(fr.x, occ.bottom, fr.width, fr.bottom - occ.bottom))
            free = new_free

        # Remove rects contained within others
        pruned: list[Rect] = []
        for i, a in enumerate(free):
            contained = False
            for j, b in enumerate(free):
                if i != j and b.contains(a) and a != b:
                    contained = True
                    break
            if not contained and a.width >= MIN_USEFUL_SIZE and a.height >= MIN_USEFUL_SIZE:
                pruned.append(a)

        self._free_rects = pruned

    @staticmethod
    def _nearest_zone(cx: float, cy: float) -> str:
        """Map center point to nearest zone name for backward compat."""
        col = "left" if cx < 640 else ("center" if cx < 1280 else "right")
        row = "top" if cy < 360 else ("center" if cy < 720 else "bottom")
        return f"{row}-{col}"
```

### 1.2 Size Estimator

New file: `backend/src/feynman/agent/size_estimator.py`

Pre-render size estimates so the solver can check "will it fit?" before the LLM commits.

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SizeEstimate:
    """Estimated rendered dimensions in board space (1920x1080)."""
    width: float
    height: float
    confidence: float  # 0-1, how reliable this estimate is

    @property
    def area(self) -> float:
        return self.width * self.height


# ── KaTeX size estimation ────────────────────────────────────
# Based on empirical measurements of KaTeX rendered output at
# the font sizes and board dimensions we use.

_KATEX_CHAR_WIDTH = 14.0     # avg width per character (board px)
_KATEX_LINE_HEIGHT = 50.0    # single-line equation height
_KATEX_FRAC_BONUS = 30.0     # extra height per fraction level
_KATEX_SQRT_BONUS = 15.0     # extra height for sqrt
_KATEX_MIN_WIDTH = 100.0
_KATEX_MAX_WIDTH = 800.0
_KATEX_PADDING = 40.0        # visual padding around equation


def estimate_equation_size(latex: str) -> SizeEstimate:
    """Estimate rendered size of a KaTeX equation.

    Not pixel-perfect — within ~20% is sufficient for placement
    decisions. The frontend will report actual bounds after render.
    """
    # Strip LaTeX commands for character counting
    stripped = latex
    for cmd in ("\\frac", "\\sqrt", "\\sum", "\\int", "\\prod",
                "\\left", "\\right", "\\htmlId", "\\text"):
        stripped = stripped.replace(cmd, "")
    # Remove braces
    stripped = stripped.replace("{", "").replace("}", "")

    char_count = len(stripped)
    width = min(max(char_count * _KATEX_CHAR_WIDTH + _KATEX_PADDING, _KATEX_MIN_WIDTH), _KATEX_MAX_WIDTH)

    # Height: base + fraction nesting + sqrt
    height = _KATEX_LINE_HEIGHT
    frac_depth = latex.count("\\frac")
    if frac_depth > 0:
        height += frac_depth * _KATEX_FRAC_BONUS
    if "\\sqrt" in latex:
        height += _KATEX_SQRT_BONUS
    # Multi-line (aligned environments)
    newlines = latex.count("\\\\")
    if newlines > 0:
        height += newlines * _KATEX_LINE_HEIGHT * 0.8

    height += _KATEX_PADDING

    return SizeEstimate(width=width, height=height, confidence=0.7)


# ── Text size estimation ─────────────────────────────────────

_TEXT_CHAR_WIDTH = 10.0
_TEXT_LINE_HEIGHT = 28.0
_TEXT_TITLE_HEIGHT = 36.0
_TEXT_MAX_WIDTH = 500.0
_TEXT_PADDING = 32.0


def estimate_text_size(text: str, title: str = "") -> SizeEstimate:
    """Estimate rendered size of a text block."""
    # Wrap width
    max_line_width = _TEXT_MAX_WIDTH
    words = text.split()
    lines = 1
    current_width = 0.0
    for word in words:
        word_width = len(word) * _TEXT_CHAR_WIDTH
        if current_width + word_width > max_line_width and current_width > 0:
            lines += 1
            current_width = word_width
        else:
            current_width += word_width + _TEXT_CHAR_WIDTH  # space

    height = lines * _TEXT_LINE_HEIGHT + _TEXT_PADDING
    if title:
        height += _TEXT_TITLE_HEIGHT
    width = min(max(len(text) * _TEXT_CHAR_WIDTH, 200), max_line_width) + _TEXT_PADDING

    return SizeEstimate(width=width, height=height, confidence=0.75)


# ── Diagram size estimation ──────────────────────────────────

_DIAGRAM_SIZES: dict[str, tuple[float, float]] = {
    "small": (300, 250),
    "medium": (500, 400),
    "large": (700, 550),
    "full": (900, 650),
}


def estimate_diagram_size(complexity: str = "medium") -> SizeEstimate:
    """Estimate diagram size from complexity hint.

    complexity: "small", "medium", "large", "full"
    """
    w, h = _DIAGRAM_SIZES.get(complexity, _DIAGRAM_SIZES["medium"])
    return SizeEstimate(width=w, height=h, confidence=0.5)


def estimate_design_diagram_size(prompt: str) -> SizeEstimate:
    """Estimate design agent diagram size from prompt complexity."""
    # Heuristic: longer/more detailed prompts → larger diagrams
    word_count = len(prompt.split())
    if word_count > 40:
        return estimate_diagram_size("large")
    elif word_count > 20:
        return estimate_diagram_size("medium")
    return estimate_diagram_size("small")


def estimate_graph_size(series_count: int = 1) -> SizeEstimate:
    """Estimate chart/graph rendered size."""
    base_w, base_h = 500, 350
    # Wider if multiple series (legend takes space)
    if series_count > 2:
        base_w += 100
    return SizeEstimate(width=base_w, height=base_h, confidence=0.7)


def estimate_scene_size(element_count: int = 3) -> SizeEstimate:
    """Estimate draw_scene component diagram size."""
    if element_count > 6:
        return estimate_diagram_size("large")
    elif element_count > 3:
        return estimate_diagram_size("medium")
    return estimate_diagram_size("small")


def estimate_step_equation_size(step_count: int = 3) -> SizeEstimate:
    """Estimate step-by-step equation derivation size."""
    width = 450
    height = step_count * 65 + 60  # per step + header
    return SizeEstimate(width=width, height=height, confidence=0.65)
```

### 1.3 Integrate Solver with SceneGraph

File: `backend/src/feynman/agent/board_state.py`

Add `spatial_solver: SpatialSolver` field. When SceneGraph updates bounds, also update the solver.

```python
# In BoardState.__init__ (or dataclass fields):
spatial_solver: SpatialSolver = field(default_factory=SpatialSolver)

# In BoardState — new method called when SceneGraph receives bounds:
def update_spatial(self, bounds_report: BoundsReportPayload) -> None:
    """Update both scene graph and spatial solver from frontend bounds."""
    self.scene_graph.update_bounds(bounds_report)
    rects: dict[str, Rect] = {}
    for el in bounds_report.elements:
        rects[el.element_id] = Rect(el.x, el.y, el.width, el.height)
    self.spatial_solver.update_all(rects)
```

### Test Criteria (Phase 1)

New file: `backend/tests/unit/test_spatial_solver.py`

- Empty board: `can_fit(any_size)` returns True
- Single large element: free space correctly computed as 4 surrounding regions
- Multiple elements: no free rect overlaps any occupied rect
- `find_placement(near=anchor, relation=RIGHT_OF)`: returns position to the right
- `find_placement(near=anchor)` when no space right: falls back to best-fit
- `reading_order()`: returns elements L→R, T→B
- `density_by_quadrant()`: correct fill percentages
- `largest_free_region()`: returns the actual largest
- All `SizeEstimate` functions return reasonable values (not zero, not board-sized)
- Solver + SceneGraph integration: bounds report updates both

**Target**: 25-30 tests.

---

## Phase 2: ASCII Board Snapshot

**Goal**: Replace the flat text board summary with a 2D ASCII render that the LLM can actually "see." No tool changes — just dramatically better prompt context. This alone is a major upgrade.

### 2.1 ASCII Snapshot Generator

New file: `backend/src/feynman/agent/board_snapshot.py`

```python
from __future__ import annotations

from feynman.agent.spatial_solver import SpatialSolver, Rect, BOARD_WIDTH, BOARD_HEIGHT


# ASCII canvas dimensions (characters)
CANVAS_COLS = 72
CANVAS_ROWS = 18
# Margins for the box border
BORDER = 1

# Scale factors: board pixels → ASCII chars
_SCALE_X = (CANVAS_COLS - 2 * BORDER) / BOARD_WIDTH
_SCALE_Y = (CANVAS_ROWS - 2 * BORDER) / BOARD_HEIGHT


def generate_snapshot(
    solver: SpatialSolver,
    board_elements: dict[str, object],
    *,
    max_label_len: int = 20,
) -> str:
    """Generate a 2D ASCII representation of the board.

    The LLM sees this instead of a flat list. Provides genuine spatial
    intuition: where things are, how much space they take, what's empty.

    Output format:
    ```
    ┌──────────────────────────────────────────────────────────────────────┐
    │ ▪"Key insight"                                                      │
    │   (text, sm)                                                        │
    │                                                                     │
    │ ┌────────────────┐                             ▪ F = ma             │
    │ │ Free Body      │                               (eq, sm)           │
    │ │ Diagram        │                                                  │
    │ │   (lg)         │                                                  │
    │ └────────────────┘                                                  │
    │                                                                     │
    │                                                                     │
    │                                                                     │
    │                                                                     │
    │                         (empty)                                     │
    │                                                                     │
    │                                                                     │
    │                                                                     │
    │                                                                     │
    └──────────────────────────────────────────────────────────────────────┘
    ```
    """
    # Initialize canvas with spaces
    canvas: list[list[str]] = [
        [" "] * CANVAS_COLS for _ in range(CANVAS_ROWS)
    ]

    # Draw border
    _draw_border(canvas)

    # Draw each element as a labeled rectangle or point
    for eid, occ_rect in solver._occupied.items():
        el = board_elements.get(eid)
        label = _get_label(el, eid, max_label_len)
        type_tag = _get_type_tag(el)
        size_tag = _get_size_tag(occ_rect)
        _draw_element(canvas, occ_rect, label, type_tag, size_tag)

    # Label empty regions
    _label_empty_regions(canvas, solver)

    # Convert canvas to string
    return "\n".join("".join(row) for row in canvas)


def generate_board_context(
    solver: SpatialSolver,
    board_elements: dict[str, object],
    teaching_scenario: str = "",
) -> str:
    """Full board context for LLM prompt: snapshot + metrics + suggestions.

    This replaces BoardState.summary() + _build_board_state_section() as
    the primary board context in the teaching prompt.
    """
    parts: list[str] = []

    # ASCII snapshot
    snapshot = generate_snapshot(solver, board_elements)
    parts.append(snapshot)

    # Metrics line
    free_pct = solver.free_space_percentage()
    density = solver.density_by_quadrant()
    busy = [name for name, pct in density.items() if pct > 0.4]
    open_q = [name for name, pct in density.items() if pct < 0.05]

    metrics: list[str] = [f"Board: {free_pct:.0%} free"]
    if busy:
        metrics.append(f"Busy: {', '.join(busy)}")
    if open_q:
        metrics.append(f"Open: {', '.join(open_q)}")
    parts.append(". ".join(metrics) + ".")

    # Reading flow
    flow = solver.reading_order()
    if flow:
        flow_labels = []
        for eid in flow[:6]:  # max 6 to keep it short
            el = board_elements.get(eid)
            label = _get_label(el, eid, 15)
            flow_labels.append(f"{eid}({label})")
        parts.append(f"Reading flow: {' -> '.join(flow_labels)}")

    # Largest free region
    largest = solver.largest_free_region()
    if largest:
        parts.append(
            f"Largest free area: {largest.width:.0f}x{largest.height:.0f}px "
            f"at ({largest.x:.0f},{largest.y:.0f})"
        )

    # Placement suggestions (computed by solver)
    suggestions = _compute_suggestions(solver, board_elements, teaching_scenario)
    if suggestions:
        parts.append("")
        parts.append("Suggested next placements:")
        for i, s in enumerate(suggestions[:3]):
            parts.append(f"  {i+1}. {s}")

    return "\n".join(parts)


def _compute_suggestions(
    solver: SpatialSolver,
    board_elements: dict[str, object],
    teaching_scenario: str,
) -> list[str]:
    """Generate 2-3 suggested placements based on board state."""
    suggestions: list[str] = []

    # Find the most recent anchor (diagram/scene) for relational suggestions
    latest_anchor_id: str | None = None
    latest_anchor_step = -1
    for eid, el in board_elements.items():
        el_type = getattr(el, "type", "")
        step = getattr(el, "created_at", 0)
        if el_type in ("draw_design_diagram", "draw_scene", "draw_diagram") and step > latest_anchor_step:
            latest_anchor_id = eid
            latest_anchor_step = step

    # Suggestion 1: Near the latest anchor
    if latest_anchor_id and latest_anchor_id in solver._occupied:
        anchor_rect = solver._occupied[latest_anchor_id]
        anchor_label = _get_label(board_elements.get(latest_anchor_id), latest_anchor_id, 20)
        # Check space to the right
        right_space = solver._width - anchor_rect.right
        if right_space > 200:
            suggestions.append(
                f"Supporting content -> near=\"{latest_anchor_id}\", "
                f"relation=\"right_of\" ({right_space:.0f}px available)"
            )
        # Check space below
        below_space = solver._height - anchor_rect.bottom
        if below_space > 150:
            suggestions.append(
                f"Follow-up content -> near=\"{latest_anchor_id}\", "
                f"relation=\"below\" ({below_space:.0f}px available)"
            )

    # Suggestion 2: Largest free region for new cluster
    largest = solver.largest_free_region()
    if largest and largest.area > 200000:  # at least ~450x450
        zone = solver._nearest_zone(largest.center_x, largest.center_y)
        suggestions.append(
            f"New concept cluster -> zone=\"{zone}\" "
            f"({largest.width:.0f}x{largest.height:.0f}px free)"
        )

    return suggestions


# ── Internal helpers ─────────────────────────────────────────

def _draw_border(canvas: list[list[str]]) -> None:
    """Draw box border on the canvas."""
    rows, cols = len(canvas), len(canvas[0])
    # Top and bottom
    for c in range(cols):
        canvas[0][c] = "─"
        canvas[rows - 1][c] = "─"
    # Left and right
    for r in range(rows):
        canvas[r][0] = "│"
        canvas[r][cols - 1] = "│"
    # Corners
    canvas[0][0] = "┌"
    canvas[0][cols - 1] = "┐"
    canvas[rows - 1][0] = "└"
    canvas[rows - 1][cols - 1] = "┘"


def _draw_element(
    canvas: list[list[str]],
    rect: Rect,
    label: str,
    type_tag: str,
    size_tag: str,
) -> None:
    """Draw a labeled element on the ASCII canvas."""
    # Convert board coords to canvas coords
    c1 = int(rect.x * _SCALE_X) + BORDER
    r1 = int(rect.y * _SCALE_Y) + BORDER
    c2 = int(rect.right * _SCALE_X) + BORDER
    r2 = int(rect.bottom * _SCALE_Y) + BORDER

    rows, cols = len(canvas), len(canvas[0])
    c1 = max(BORDER, min(c1, cols - BORDER - 1))
    r1 = max(BORDER, min(r1, rows - BORDER - 1))
    c2 = max(c1 + 2, min(c2, cols - BORDER - 1))
    r2 = max(r1 + 1, min(r2, rows - BORDER - 1))

    el_width = c2 - c1
    el_height = r2 - r1

    if el_width >= 6 and el_height >= 3:
        # Large enough to draw a box
        _draw_box(canvas, r1, c1, r2, c2)
        # Label inside the box
        _write_text(canvas, r1 + 1, c1 + 2, label[:el_width - 4])
        if el_height >= 4:
            tag = f"({type_tag}, {size_tag})"
            _write_text(canvas, r1 + 2, c1 + 2, tag[:el_width - 4])
    else:
        # Small — just a marker + label
        _write_text(canvas, r1, c1, f"* {label[:el_width + 8]}")
        if r1 + 1 < rows - BORDER:
            tag = f"  ({type_tag}, {size_tag})"
            _write_text(canvas, r1 + 1, c1, tag[:el_width + 8])


def _draw_box(canvas: list[list[str]], r1: int, c1: int, r2: int, c2: int) -> None:
    """Draw a rectangle outline on the canvas."""
    for c in range(c1, c2 + 1):
        if 0 <= r1 < len(canvas) and 0 <= c < len(canvas[0]):
            canvas[r1][c] = "─"
        if 0 <= r2 < len(canvas) and 0 <= c < len(canvas[0]):
            canvas[r2][c] = "─"
    for r in range(r1, r2 + 1):
        if 0 <= r < len(canvas) and 0 <= c1 < len(canvas[0]):
            canvas[r][c1] = "│"
        if 0 <= r < len(canvas) and 0 <= c2 < len(canvas[0]):
            canvas[r][c2] = "│"
    if 0 <= r1 < len(canvas) and 0 <= c1 < len(canvas[0]):
        canvas[r1][c1] = "┌"
    if 0 <= r1 < len(canvas) and 0 <= c2 < len(canvas[0]):
        canvas[r1][c2] = "┐"
    if 0 <= r2 < len(canvas) and 0 <= c1 < len(canvas[0]):
        canvas[r2][c1] = "└"
    if 0 <= r2 < len(canvas) and 0 <= c2 < len(canvas[0]):
        canvas[r2][c2] = "┘"


def _write_text(canvas: list[list[str]], row: int, col: int, text: str) -> None:
    """Write text onto the canvas at a position (clamped to bounds)."""
    if row < 0 or row >= len(canvas):
        return
    for i, ch in enumerate(text):
        c = col + i
        if BORDER <= c < len(canvas[0]) - BORDER:
            canvas[row][c] = ch


def _label_empty_regions(canvas: list[list[str]], solver: SpatialSolver) -> None:
    """Write '(empty)' in large empty areas of the canvas."""
    largest = solver.largest_free_region()
    if not largest or largest.area < 100000:
        return
    cr = int(largest.center_y * _SCALE_Y) + BORDER
    cc = int(largest.center_x * _SCALE_X) + BORDER
    _write_text(canvas, cr, cc - 3, "(empty)")


def _get_label(el: object | None, eid: str, max_len: int) -> str:
    if el is None:
        return eid
    label = getattr(el, "label", "") or eid
    return label[:max_len]


def _get_type_tag(el: object | None) -> str:
    if el is None:
        return "?"
    t = getattr(el, "type", "")
    short = {
        "show_text": "txt", "show_equation": "eq",
        "draw_diagram": "diag", "draw_design_diagram": "design",
        "draw_scene": "scene", "step_equation": "steps",
        "show_graph": "graph",
    }
    return short.get(t, t[:6])


def _get_size_tag(rect: Rect) -> str:
    area = rect.area
    board_area = BOARD_WIDTH * BOARD_HEIGHT
    ratio = area / board_area
    if ratio > 0.08:
        return "lg"
    if ratio > 0.02:
        return "md"
    return "sm"
```

### 2.2 Wire into Prompt Assembly

File: `backend/src/feynman/agent/prompts.py` — `_build_board_state_section()`

Replace the current flat summary with the ASCII snapshot. The board summary priority becomes:

1. **ASCII snapshot** (from Board Cortex) — when spatial solver has data
2. **Clustered summary** (from BoardGraph) — fallback
3. **Flat zone listing** — last resort

### Test Criteria (Phase 2)

New file: `backend/tests/unit/test_board_snapshot.py`

- Empty board: snapshot shows only border + "(empty)"
- Single small element: shown as `*` marker with label
- Single large element: shown as box with label inside
- Multiple elements: all rendered without overlapping text
- Board metrics line: correct free %, busy/open quadrants
- Reading flow: correct L→R, T→B order
- Suggestions: reasonable next placements based on board state
- `generate_board_context()` includes all sections

**Target**: 15-20 tests.

---

## Phase 3: Placement Intent Schema

**Goal**: Give the LLM a new vocabulary for spatial decisions. Instead of picking from 9 zones, it expresses semantic intent: "near design-1, right_of." Backward compatible — zone still works.

### 3.1 Extend `_BaseInstruction` with Position Fields

File: `backend/src/feynman/visuals/schemas.py`

```python
class PlacementIntent(BaseModel):
    """Semantic placement intent from the LLM.

    The LLM outputs one of:
    1. near + relation: place relative to an existing element
    2. zone: backward-compatible zone placement
    3. Neither: solver picks best position automatically
    """
    near: str | None = None            # element_id to place near
    relation: str | None = None        # right_of, below, above, left_of
    size_hint: str = "medium"          # small, medium, large, full-width

class _BaseInstruction(BaseModel):
    """Fields shared by all visual instructions."""
    element_id: str | None = None
    duration_ms: int | None = None
    sync_mode: SyncMode = SyncMode.ON_PLAYOUT
    term_hints: list[TermSyncHint] | None = None
    zone: BoardZone | None = None
    board_id: str | None = None
    # NEW — Board Cortex fields
    position_x: float | None = None    # exact x from solver (sent to frontend)
    position_y: float | None = None    # exact y from solver (sent to frontend)
    placement: PlacementIntent | None = None  # LLM intent (not sent to frontend)
```

### 3.2 Frontend: Support Exact Position

File: `frontend/src/engine/whiteboard/WhiteboardScene.tsx`

When `position_x` and `position_y` are set, render at those exact coordinates instead of using zone-based placement. Zone remains as fallback.

```typescript
// In element rendering:
if (instruction.position_x != null && instruction.position_y != null) {
  // Exact placement from Board Cortex
  style = {
    position: "absolute",
    left: `${instruction.position_x}px`,
    top: `${instruction.position_y}px`,
  };
} else if (instruction.zone) {
  // Zone-based placement (backward compat)
  // ... existing zone layout logic
}
```

File: `frontend/src/engine/whiteboard/types.ts`

```typescript
// Add to Rect or PlacedElement:
export interface PositionedElement extends PlacedElement {
  /** Exact position from backend solver (overrides zone placement). */
  positionX?: number;
  positionY?: number;
}
```

### 3.3 Update Wire Protocol

File: `contracts/visuals.schema.json`

Add `position_x`, `position_y` as optional number fields to the base instruction schema. Add `placement` as an object (never sent to frontend — stripped in `_publish_visual`).

File: `frontend/src/types/visuals.ts`

Mirror the new fields.

### Test Criteria (Phase 3)

- `PlacementIntent` serialization/deserialization
- `_BaseInstruction` with position_x/y: serializes correctly, excluded when None
- `placement` field stripped before publish (not sent to frontend)
- Frontend: element renders at exact (x, y) when position fields present
- Frontend: falls back to zone placement when position fields absent
- Backward compat: existing instructions without new fields still work

**Target**: 12-15 tests (backend + frontend).

---

## Phase 4: Placement Executor

**Goal**: Wire intent → solver → exact coordinates. This is where the magic happens: the LLM says "near design-1, right", and the system computes exact pixel coordinates.

### 4.1 Placement Executor

New file: `backend/src/feynman/agent/placement_executor.py`

```python
from __future__ import annotations

import structlog

from feynman.agent.spatial_solver import SpatialSolver, SpatialRelation, PlacementResult
from feynman.agent.size_estimator import (
    estimate_equation_size,
    estimate_text_size,
    estimate_design_diagram_size,
    estimate_diagram_size,
    estimate_graph_size,
    estimate_scene_size,
    estimate_step_equation_size,
    SizeEstimate,
)
from feynman.visuals.schemas import _BaseInstruction, PlacementIntent, BoardZone

logger = structlog.get_logger()

# Map string relations to solver enum
_RELATION_MAP: dict[str, SpatialRelation] = {
    "right_of": SpatialRelation.RIGHT_OF,
    "left_of": SpatialRelation.LEFT_OF,
    "below": SpatialRelation.BELOW,
    "above": SpatialRelation.ABOVE,
    "centered": SpatialRelation.CENTERED,
}

# Zone centers for fallback zone→coordinate conversion
_ZONE_CENTERS: dict[str, tuple[float, float]] = {
    "top-left": (240, 150),
    "top-center": (960, 150),
    "top-right": (1680, 150),
    "center-left": (240, 540),
    "center-center": (960, 540),
    "center-right": (1680, 540),
    "bottom-left": (240, 900),
    "bottom-center": (960, 900),
    "bottom-right": (1680, 900),
}


def resolve_placement(
    instruction: _BaseInstruction,
    solver: SpatialSolver,
) -> None:
    """Resolve placement intent into exact position coordinates.

    Modifies the instruction in-place, setting position_x and position_y.
    Falls back gracefully: intent → zone → solver best-fit → center.

    Called in _publish_visual() before sending to frontend.
    """
    # Estimate size for this instruction type
    size = _estimate_size(instruction)

    # Strategy 1: PlacementIntent with near + relation
    if instruction.placement:
        result = _resolve_intent(instruction.placement, size, solver)
        if result:
            instruction.position_x = result.x
            instruction.position_y = result.y
            logger.debug(
                "placement.resolved",
                strategy="intent",
                element_id=instruction.element_id,
                x=result.x, y=result.y,
                reason=result.reason,
            )
            return

    # Strategy 2: Zone → coordinate (use zone center as anchor point,
    # then solver adjusts for collisions)
    if instruction.zone:
        result = _resolve_zone(instruction.zone, size, solver)
        if result:
            instruction.position_x = result.x
            instruction.position_y = result.y
            logger.debug(
                "placement.resolved",
                strategy="zone",
                element_id=instruction.element_id,
                zone=instruction.zone.value,
                x=result.x, y=result.y,
            )
            return

    # Strategy 3: Solver picks best available position
    result = solver.find_placement(size.width, size.height)
    if result:
        instruction.position_x = result.x
        instruction.position_y = result.y
        logger.debug(
            "placement.resolved",
            strategy="auto",
            element_id=instruction.element_id,
            x=result.x, y=result.y,
            reason=result.reason,
        )
        return

    # Strategy 4: Board is full — center of board (scroll suggestion will fire)
    logger.warning(
        "placement.no_space",
        element_id=instruction.element_id,
        type=instruction.type,
    )


def _resolve_intent(
    intent: PlacementIntent,
    size: SizeEstimate,
    solver: SpatialSolver,
) -> PlacementResult | None:
    """Resolve a PlacementIntent to exact coordinates."""
    relation = _RELATION_MAP.get(intent.relation or "right_of", SpatialRelation.RIGHT_OF)

    if intent.near:
        return solver.find_placement(
            size.width, size.height,
            anchor_id=intent.near,
            relation=relation,
        )

    # No anchor — just use solver's best-fit
    return solver.find_placement(size.width, size.height)


def _resolve_zone(
    zone: BoardZone,
    size: SizeEstimate,
    solver: SpatialSolver,
) -> PlacementResult | None:
    """Convert zone to coordinates using solver for collision avoidance."""
    # Use zone center as a virtual anchor point
    center = _ZONE_CENTERS.get(zone.value)
    if not center:
        return None

    cx, cy = center
    # Try to place centered on the zone
    x = cx - size.width / 2
    y = cy - size.height / 2

    from feynman.agent.spatial_solver import Rect, ELEMENT_PADDING
    candidate = Rect(x, y, size.width, size.height)

    # Check bounds
    if x < 0:
        x = ELEMENT_PADDING
    if y < 0:
        y = ELEMENT_PADDING
    if x + size.width > solver._width:
        x = solver._width - size.width - ELEMENT_PADDING
    if y + size.height > solver._height:
        y = solver._height - size.height - ELEMENT_PADDING

    # Check collisions — if the zone center is blocked, nudge
    if solver._overlaps_any(Rect(x, y, size.width, size.height)):
        # Fall back to solver's placement near this area
        return solver.find_placement(size.width, size.height)

    return PlacementResult(
        x=x, y=y, width=size.width, height=size.height,
        confidence=0.8, zone_hint=zone.value,
        reason=f"zone {zone.value} center",
    )


def _estimate_size(instruction: _BaseInstruction) -> SizeEstimate:
    """Estimate the rendered size of an instruction."""
    itype = instruction.type

    if itype == "show_equation":
        latex = getattr(instruction, "latex", "") or ""
        return estimate_equation_size(latex)
    elif itype == "show_text":
        text = getattr(instruction, "text", "") or ""
        title = getattr(instruction, "title", "") or ""
        return estimate_text_size(text, title)
    elif itype == "draw_design_diagram":
        prompt = getattr(instruction, "prompt", "") or ""
        return estimate_design_diagram_size(prompt)
    elif itype == "draw_diagram":
        nodes = getattr(instruction, "nodes", None) or []
        return estimate_diagram_size(
            "large" if len(nodes) > 6 else "medium" if len(nodes) > 3 else "small"
        )
    elif itype == "draw_scene":
        elements = getattr(instruction, "elements", None) or []
        return estimate_scene_size(len(elements))
    elif itype == "step_equation":
        steps = getattr(instruction, "steps", None) or []
        return estimate_step_equation_size(len(steps))
    elif itype == "show_graph":
        series = getattr(instruction, "series", None) or []
        return estimate_graph_size(len(series))
    else:
        # Default medium
        return SizeEstimate(width=400, height=300, confidence=0.3)
```

### 4.2 Hook into `_publish_visual`

File: `backend/src/feynman/agent/tools.py`

In `_publish_visual()`, call the placement executor before sending to frontend:

```python
from feynman.agent.placement_executor import resolve_placement

async def _publish_visual(ctx, instruction, *, wait_for_speech=None):
    tc: TeachingContext = ctx.userdata

    # Auto-assign element_id ...
    # (existing code)

    # NEW: Resolve placement intent → exact coordinates
    board_state = tc.board_manager.active_board.state
    resolve_placement(instruction, board_state.spatial_solver)

    # Strip placement intent before sending to frontend
    # (frontend only needs position_x/y, not the intent object)
    instruction.placement = None

    # (rest of existing publish code)
```

### 4.3 Parse Placement Intent from LLM Tool Calls

File: `backend/src/feynman/agent/tools.py`

Each visual tool function needs to accept and forward `near`, `relation`, `size_hint` params:

```python
@function_tool
async def show_equation(
    ctx: RunContext,
    latex: str,
    # ... existing params ...
    near: str = "",         # NEW
    relation: str = "",     # NEW
    size_hint: str = "",    # NEW
) -> str:
    instruction = ShowEquationInstruction(
        latex=latex,
        zone=_parse_zone(zone),
        # ... existing fields ...
    )
    # NEW: Attach placement intent
    if near or relation or size_hint:
        instruction.placement = PlacementIntent(
            near=near or None,
            relation=relation or None,
            size_hint=size_hint or "medium",
        )
    await _publish_visual(ctx, instruction)
    # ...
```

### Test Criteria (Phase 4)

New file: `backend/tests/unit/test_placement_executor.py`

- Intent with `near` + `relation`: resolves to position adjacent to anchor
- Intent with `near` but no space: falls back to solver best-fit
- Zone → position: maps to correct coordinates
- Zone with collision: nudges away from overlap
- No intent, no zone: solver picks best position
- Board full: logs warning, doesn't crash
- Size estimation: each instruction type returns reasonable estimates
- `_publish_visual` integration: position_x/y set before publish
- `placement` field stripped before publish (not in JSON sent to frontend)

**Target**: 20-25 tests.

---

## Phase 5: Tool Docstrings & Prompt Rewrite

**Goal**: Teach the LLM to use placement intent instead of zones. Update all tool docstrings, rewrite zone placement instructions, integrate ASCII snapshot into prompt.

### 5.1 Rewrite Tool Docstrings

File: `backend/src/feynman/agent/tools.py`

Every visual tool's docstring gets updated to teach the LLM about placement intent:

```python
async def show_equation(
    ctx: RunContext,
    latex: str,
    label: str = "",
    animation: str = "fade_in",
    # ... existing params ...
    zone: str = "",
    near: str = "",
    relation: str = "",
    size_hint: str = "",
    # ...
) -> str:
    """Display a math equation on the classroom screen.

    Args:
        ...
        zone: Fallback zone placement (9-zone grid). Prefer near+relation for
            precise placement.
        near: Place this near an existing element. Pass the element ID
            (e.g., "design-1", "eq-2"). The system computes exact position.
        relation: Spatial relationship to the `near` element.
            Options: "right_of" (default), "below", "above", "left_of".
        size_hint: Expected size: "small", "medium" (default), "large".
            Helps the system check if it fits before placing.
    """
```

### 5.2 Rewrite Placement Instructions

File: `backend/src/feynman/agent/prompts.py`

Replace `ZONE_PLACEMENT_INSTRUCTIONS` with new instructions that teach placement intent:

```python
PLACEMENT_INSTRUCTIONS = """\

## Board Placement — Think Like a Teacher

You control WHERE things appear on the board. Look at the Board State snapshot
above before every visual tool call.

### How to Place Elements

**Option 1: Near an existing element (PREFERRED)**
When the new element relates to something already on the board:
```
show_equation(latex="F=ma", near="design-1", relation="right_of")
```
Available relations: right_of, below, above, left_of.

**Option 2: Zone placement (for new clusters)**
When starting fresh content with no relation to existing elements:
```
draw_design_diagram(prompt="...", zone="center-left")
```

**Option 3: Auto-placement (when unsure)**
Omit both — the system picks the best available position:
```
show_text(text="Remember: F=ma means...")
```

### Spatial Rules

1. **Related → adjacent**: Equation for a diagram → place near that diagram.
2. **Reading flow**: New content below or right of previous content.
3. **One anchor per cluster**: One main diagram, supporting content around it.
4. **Check the snapshot**: The Board State shows exactly what's where and what's free.
5. **Trust the suggestions**: The "Suggested next placements" are computed from
   actual available space — they always fit.
6. **Size matters**: Use size_hint="large" for diagrams, "small" for equations.
   The system checks if it fits before placing.

### Teaching Scenario Patterns

Match your scenario and follow the placement flow:

**Concept Introduction**: Main diagram (zone="center-left") → equation near diagram
(near="design-1", relation="right_of") → title above (near="design-1", relation="above")

**Step-by-step Derivation**: Starting equation at top → each step below the previous
(near="step-N", relation="below") → result highlighted at bottom

**Problem Solving**: Given/find text (zone="top-right") → diagram (zone="center-left")
→ solution steps near diagram (near="design-1", relation="right_of")

**Comparison**: Case A left (zone="center-left") → Case B right (zone="center-right")
→ shared insight below (zone="bottom-center")
"""
```

### 5.3 Replace Board State Section

File: `backend/src/feynman/agent/prompts.py` — `_build_board_state_section()`

Replace the current summary with the ASCII snapshot from `board_snapshot.py`:

```python
def _build_board_state_section(teaching_ctx: TeachingContext) -> str:
    bm = teaching_ctx.board_manager
    board_state = bm.active_board.state
    solver = board_state.spatial_solver

    # Generate ASCII snapshot + metrics + suggestions
    from feynman.agent.board_snapshot import generate_board_context
    context = generate_board_context(
        solver,
        board_state._elements,
        teaching_scenario="",  # TODO: infer from lesson plan
    )

    # Viewport / scroll info (keep existing)
    # ...

    return f"\n## Board State\n\n```\n{context}\n```\n"
```

### Test Criteria (Phase 5)

- Prompt includes ASCII snapshot (not flat list) when solver has data
- Prompt falls back to flat list when solver has no bounds data
- Tool docstrings include `near`, `relation`, `size_hint` params
- Placement instructions reference all 4 teaching scenarios
- Integration test: full prompt generation with populated board

**Target**: 10-12 tests.

---

## Phase 6: Scenario-Aware Layout Planner

**Goal**: The solver pre-allocates space for entire teaching patterns. When the agent starts a concept introduction, the system reserves space for diagram + equation + title, not just the first element.

### 6.1 Teaching Scenario Detector

New file: `backend/src/feynman/agent/scenario_planner.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from feynman.agent.spatial_solver import SpatialSolver, Rect, SpatialRelation


class TeachingScenario(StrEnum):
    CONCEPT_INTRO = "concept_intro"
    DERIVATION = "derivation"
    PROBLEM_SOLVING = "problem_solving"
    COMPARISON = "comparison"
    SINGLE_FOCUS = "single_focus"
    FREE_FORM = "free_form"


@dataclass
class ScenarioSlot:
    """A reserved area for a planned element in a teaching scenario."""
    role: str            # "main_diagram", "key_equation", "title", "steps", etc.
    rect: Rect           # reserved area on the board
    filled: bool = False # True once an element has been placed here
    element_id: str = "" # ID of the element that filled this slot


@dataclass
class ScenarioPlan:
    """Pre-allocated layout for a teaching scenario."""
    scenario: TeachingScenario
    slots: list[ScenarioSlot]

    def next_unfilled(self) -> ScenarioSlot | None:
        for slot in self.slots:
            if not slot.filled:
                return slot
        return None

    def fill_slot(self, role: str, element_id: str) -> None:
        for slot in self.slots:
            if slot.role == role and not slot.filled:
                slot.filled = True
                slot.element_id = element_id
                return


def detect_scenario(
    concept_description: str,
    visual_suggestions: list[str] | None = None,
) -> TeachingScenario:
    """Detect the teaching scenario from concept metadata.

    Uses keyword matching on concept description and visual suggestions
    to determine the likely teaching pattern.
    """
    desc = concept_description.lower()
    suggestions = " ".join(visual_suggestions or []).lower()

    if any(kw in desc for kw in ("derive", "proof", "show that", "step by step")):
        return TeachingScenario.DERIVATION
    if any(kw in desc for kw in ("compare", "contrast", "difference between", "vs")):
        return TeachingScenario.COMPARISON
    if any(kw in desc for kw in ("problem", "solve", "calculate", "find the")):
        return TeachingScenario.PROBLEM_SOLVING
    if any(kw in desc for kw in ("equation", "formula", "law")) and not suggestions:
        return TeachingScenario.SINGLE_FOCUS
    if any(kw in suggestions for kw in ("diagram", "draw", "illustrat", "apparatus")):
        return TeachingScenario.CONCEPT_INTRO

    return TeachingScenario.CONCEPT_INTRO  # default


def plan_scenario(
    scenario: TeachingScenario,
    solver: SpatialSolver,
) -> ScenarioPlan:
    """Pre-allocate board space for a teaching scenario.

    Returns a ScenarioPlan with reserved slots. The Placement Executor
    uses these slots as preferred positions when the LLM creates visuals.
    """
    W, H = solver._width, solver._height
    PAD = 40

    if scenario == TeachingScenario.CONCEPT_INTRO:
        return ScenarioPlan(
            scenario=scenario,
            slots=[
                ScenarioSlot("title", Rect(PAD, PAD, W * 0.5, 80)),
                ScenarioSlot("main_diagram", Rect(PAD, 140, W * 0.45, H * 0.55)),
                ScenarioSlot("key_equation", Rect(W * 0.52, 140, W * 0.42, 120)),
                ScenarioSlot("supporting_text", Rect(W * 0.52, 280, W * 0.42, 200)),
                ScenarioSlot("follow_up", Rect(PAD, H * 0.72, W - 2 * PAD, H * 0.24)),
            ],
        )
    elif scenario == TeachingScenario.DERIVATION:
        return ScenarioPlan(
            scenario=scenario,
            slots=[
                ScenarioSlot("reference_diagram", Rect(PAD, PAD, W * 0.25, H * 0.4)),
                ScenarioSlot("starting_equation", Rect(W * 0.3, PAD, W * 0.4, 80)),
                ScenarioSlot("steps", Rect(W * 0.3, 140, W * 0.4, H * 0.6)),
                ScenarioSlot("annotations", Rect(W * 0.75, 140, W * 0.2, H * 0.5)),
                ScenarioSlot("result", Rect(W * 0.3, H * 0.8, W * 0.4, 100)),
            ],
        )
    elif scenario == TeachingScenario.PROBLEM_SOLVING:
        return ScenarioPlan(
            scenario=scenario,
            slots=[
                ScenarioSlot("given_find", Rect(W * 0.6, PAD, W * 0.35, 150)),
                ScenarioSlot("diagram", Rect(PAD, PAD, W * 0.5, H * 0.55)),
                ScenarioSlot("solution_steps", Rect(W * 0.55, 200, W * 0.4, H * 0.45)),
                ScenarioSlot("answer", Rect(W * 0.55, H * 0.7, W * 0.4, 120)),
            ],
        )
    elif scenario == TeachingScenario.COMPARISON:
        mid = W * 0.5
        return ScenarioPlan(
            scenario=scenario,
            slots=[
                ScenarioSlot("case_a_title", Rect(PAD, PAD, mid - 2 * PAD, 80)),
                ScenarioSlot("case_b_title", Rect(mid + PAD, PAD, mid - 2 * PAD, 80)),
                ScenarioSlot("case_a_visual", Rect(PAD, 140, mid - 2 * PAD, H * 0.45)),
                ScenarioSlot("case_b_visual", Rect(mid + PAD, 140, mid - 2 * PAD, H * 0.45)),
                ScenarioSlot("shared_insight", Rect(W * 0.2, H * 0.7, W * 0.6, 150)),
            ],
        )
    elif scenario == TeachingScenario.SINGLE_FOCUS:
        return ScenarioPlan(
            scenario=scenario,
            slots=[
                ScenarioSlot("main_equation", Rect(W * 0.15, H * 0.25, W * 0.7, 200)),
                ScenarioSlot("annotation", Rect(W * 0.15, H * 0.6, W * 0.7, 200)),
            ],
        )
    else:
        # Free form — no pre-allocated slots
        return ScenarioPlan(scenario=scenario, slots=[])
```

### 6.2 Integrate with Concept Advance

File: `backend/src/feynman/agent/tools.py` — in `advance_concept()`

When the agent advances to a new concept, detect the scenario and pre-plan the layout:

```python
# After advancing concept:
from feynman.agent.scenario_planner import detect_scenario, plan_scenario

concept = tc.lesson_plan.concepts[new_index]
scenario = detect_scenario(concept.description, concept.visual_suggestions)
plan = plan_scenario(scenario, board_state.spatial_solver)
board_state.scenario_plan = plan  # new field on BoardState
```

### 6.3 Placement Executor Uses Scenario Slots

File: `backend/src/feynman/agent/placement_executor.py`

Before the general placement logic, check if there's an unfilled scenario slot that matches this element type:

```python
def resolve_placement(instruction, solver):
    # NEW: Check scenario plan first
    if hasattr(board_state, 'scenario_plan') and board_state.scenario_plan:
        slot = _match_slot(instruction, board_state.scenario_plan)
        if slot:
            instruction.position_x = slot.rect.x
            instruction.position_y = slot.rect.y
            slot.filled = True
            slot.element_id = instruction.element_id
            return

    # ... existing resolution logic ...
```

### 6.4 Scenario in Prompt

Include the active scenario plan in the board state section:

```
Scenario: CONCEPT INTRODUCTION
  [x] title — text-1 (Newton's Second Law)
  [x] main_diagram — design-1 (Free body diagram)
  [ ] key_equation — (unfilled, space reserved right of diagram)
  [ ] supporting_text — (unfilled, below equation area)
  [ ] follow_up — (unfilled, bottom row)
```

### Test Criteria (Phase 6)

- `detect_scenario()`: correct detection from concept descriptions
- `plan_scenario()`: correct slot layout for each scenario type
- Slots don't overlap each other within a scenario
- Slot matching: equation → key_equation slot, diagram → main_diagram slot
- `fill_slot()`: marks slot as filled, stores element_id
- `next_unfilled()`: returns correct next slot
- Prompt includes scenario status when plan is active
- Integration: advance_concept triggers scenario detection + planning

**Target**: 20-25 tests.

---

## Phase 7: Board Flow Intelligence

**Goal**: The system becomes aware of visual flow, density balance, and temporal narrative. It can suggest when to scroll, when to erase, and how to maintain visual coherence across the lesson.

### 7.1 Flow Analyzer

New method on `SpatialSolver`:

```python
def flow_analysis(self, board_elements: dict[str, object]) -> FlowAnalysis:
    """Analyze the visual flow and health of the board.

    Returns:
        - reading_direction: dominant flow (L→R, T→B, or mixed)
        - density_balance: how evenly distributed content is
        - visual_weight_center: center of mass of all elements
        - crowding_zones: areas that are too dense
        - suggested_action: "continue", "scroll_right", "clear_old", "rebalance"
    """
```

### 7.2 Scroll Advisor

```python
def should_scroll(self, board_elements: dict[str, object]) -> ScrollAdvice | None:
    """Recommend scrolling when the board is getting full.

    Smarter than the current "6+ zones occupied" heuristic.
    Considers:
    - Overall density (not just zone count)
    - Where the active content is (don't scroll away from recent work)
    - Reading direction (prefer scrolling right)
    - Whether upcoming content can fit in remaining space
    """
```

### 7.3 Erase Advisor

```python
def suggest_cleanup(
    self,
    board_elements: dict[str, object],
    current_concept_index: int,
) -> list[str]:
    """Suggest element IDs safe to erase.

    Criteria:
    - From a completed concept (not current or upcoming)
    - Not referenced by any active relationship edge
    - Not an anchor of a cluster that's still relevant
    - Prefer erasing oldest elements first
    """
```

### 7.4 Space Reservation for Upcoming Content

Using the anticipation engine's knowledge of upcoming concepts:

```python
def reserve_for_upcoming(
    self,
    upcoming_concepts: list[ConceptNode],
    count: int = 1,
) -> list[ReservationHint]:
    """Hint about space needed for upcoming concepts.

    Adds "upcoming" markers to the ASCII snapshot so the LLM
    sees: "Reserved: ~500x400px bottom-center for 'Worked Example'"
    """
```

### Test Criteria (Phase 7)

- `flow_analysis()`: correct reading direction, density balance
- `should_scroll()`: recommends scroll when density > 70%, not at 30%
- `should_scroll()`: doesn't recommend scroll away from recent work
- `suggest_cleanup()`: never suggests current concept's elements
- `suggest_cleanup()`: respects active relationship edges
- `reserve_for_upcoming()`: correct size estimates from concept metadata
- Integration: scroll advice appears in board snapshot suggestions

**Target**: 18-22 tests.

---

## Phase 8: Visual Verification Loop

**Goal**: Async verification that the board looks good after rendering. Uses a fast vision model (Haiku-class) to spot layout issues — overlapping text, awkward spacing, unreadable labels. NOT in the hot path.

### 8.1 Board Screenshot Capture

File: `frontend/src/engine/whiteboard/BoardCapture.tsx`

New headless component that captures the board as a PNG data URL on demand (triggered by a data channel message from backend).

```typescript
// Captures the board surface as a compressed PNG (max 512x288 — small, fast)
// Sends back via data channel topic "board_capture"
```

### 8.2 Verification Agent

New file: `backend/src/feynman/agent/board_verifier.py`

```python
class BoardVerifier:
    """Async visual verification of board layout quality.

    Captures a board screenshot, sends to a fast vision model,
    and returns a quality assessment. NOT blocking — runs in background
    after diagram placements.

    Triggers: only after draw_design_diagram or draw_scene (expensive visuals).
    Frequency: at most once per concept (not every element).
    """

    async def verify_board(self, screenshot_b64: str, board_context: str) -> VerificationResult:
        """Send board screenshot to vision model for layout check.

        Prompt: "You are checking a classroom whiteboard layout.
        Is the content readable? Any overlapping elements? Awkward spacing?
        Score 1-5 and list specific issues if any."

        Model: Claude Haiku (fast, cheap) with vision
        """

    async def suggest_fixes(self, result: VerificationResult) -> list[FixAction]:
        """If issues detected, suggest concrete fixes.

        E.g.: "move eq-2 right by 50px to avoid overlap with design-1"
        These can be applied automatically or flagged for the teaching agent.
        """
```

### 8.3 Integration

File: `backend/src/feynman/agent/tools.py`

After `draw_design_diagram` and `draw_scene`, fire background verification:

```python
# At the end of draw_design_diagram, after publish:
if tc.board_verifier and not tc._verified_this_concept:
    asyncio.create_task(tc.board_verifier.request_verification())
    tc._verified_this_concept = True
```

### Test Criteria (Phase 8)

- Verification request sent after draw_design_diagram (not after show_text)
- At most one verification per concept
- Verification result parsed correctly
- Fix suggestions are actionable (element_id + direction + distance)
- Verification doesn't block the teaching flow
- Frontend captures board at correct resolution
- Data channel round-trip works

**Target**: 12-15 tests.

---

## Phase 9: Polish, Testing & Edge Cases

**Goal**: Integration testing, edge cases, performance, backward compatibility.

### 9.1 Edge Cases

- Board with 0 elements (empty) → all systems return sensible defaults
- Board with 1 massive element filling 80% of space → solver finds remaining 20%
- 20+ elements (dense board) → solver performs < 5ms
- Infinite canvas: solver respects viewport tile, not just board dimensions
- Multi-board: solver state is per-board, restored on switch_board
- Doubt branch: solver state pushed/popped with board stack
- Rapid-fire tool calls: solver handles sequential updates correctly

### 9.2 Performance Validation

- `_rebuild_free_rects()` < 2ms for 20 occupied elements
- `find_placement()` < 1ms
- `generate_snapshot()` < 5ms
- Size estimation < 0.1ms
- Full `resolve_placement()` pipeline < 3ms

### 9.3 Backward Compatibility

- All existing tests pass without modification
- Tools that only use `zone` (no `near`/`relation`) still work
- Frontend renders correctly with zone-only instructions
- Board summary falls back to flat list when solver has no bounds data

### 9.4 Prompt Tuning

- A/B test ASCII snapshot vs flat list with real teaching scenarios
- Tune suggestion quality based on observed agent behavior
- Adjust size estimation constants from actual render measurements

### Test Criteria (Phase 9)

- Full integration test: concept advance → scenario plan → 3 tool calls → verify placements don't overlap
- Performance benchmarks pass
- All pre-existing tests still pass (489 backend, 187 frontend)
- Graceful degradation: solver with no bounds data → zone fallback → center fallback

**Target**: 15-20 integration tests + all existing tests green.

---

## Phase Summary

| # | Phase | New Files | Modified Files | Est. Tests |
|---|-------|-----------|----------------|------------|
| 1 | Spatial Solver + Size Estimator | `spatial_solver.py`, `size_estimator.py`, `test_spatial_solver.py` | `board_state.py` | 25-30 |
| 2 | ASCII Board Snapshot | `board_snapshot.py`, `test_board_snapshot.py` | `prompts.py` | 15-20 |
| 3 | Placement Intent Schema | — | `schemas.py`, `WhiteboardScene.tsx`, `types.ts`, `visuals.schema.json`, `visuals.ts` | 12-15 |
| 4 | Placement Executor | `placement_executor.py`, `test_placement_executor.py` | `tools.py` | 20-25 |
| 5 | Tool Docstrings & Prompt Rewrite | — | `tools.py`, `prompts.py` | 10-12 |
| 6 | Scenario-Aware Layout | `scenario_planner.py`, `test_scenario_planner.py` | `tools.py`, `board_state.py`, `prompts.py` | 20-25 |
| 7 | Board Flow Intelligence | — | `spatial_solver.py`, `board_snapshot.py`, `prompts.py` | 18-22 |
| 8 | Visual Verification Loop | `board_verifier.py`, `BoardCapture.tsx` | `tools.py`, `teaching_context.py` | 12-15 |
| 9 | Polish & Edge Cases | integration test files | various | 15-20 |

**Total new tests**: ~150-185
**Cumulative with existing**: ~640-675 backend, ~200+ frontend

---

## Key Architectural Decisions

1. **LLM never outputs pixel coordinates.** It outputs semantic intent (near, relation, size_hint) or zone. The solver translates.

2. **Solver is synchronous and sub-millisecond.** No async, no API calls. Pure geometry. Called in the hot path of every visual tool call.

3. **ASCII snapshot replaces flat summary.** The LLM gets a 2D text render of the board, not a flat list. Research shows LLMs reason better with 2D text than coordinate lists.

4. **Scenario planning is optional enhancement.** If scenario detection is wrong, the solver's general placement still works. Scenarios improve layout, don't gate correctness.

5. **Backward compatible.** Zone-only tool calls still work. Frontend handles both zone-based and position-based placement. Flat summary is the fallback when solver has no data.

6. **Visual verification is async background.** Never blocks teaching. Fires after expensive visuals, at most once per concept. Cheap model (Haiku).

7. **Size estimation is approximate.** Within ~20% is fine. Frontend reports actual bounds after render, which corrects the solver's model. The estimate just needs to be good enough for "will it fit?" checks.

8. **No infinite canvas changes in solver.** The solver works on the current viewport (1920x1080). Scrolling creates a fresh solver state for the new tile. Cross-tile awareness stays in BoardState's offscreen_summary.

---

## What This Achieves

After all 9 phases, the teaching agent:

- **Sees** the board via a 2D ASCII snapshot (not a flat text list)
- **Knows** how much space is free, where it is, and how big things are
- **Places** content relative to existing elements ("next to the diagram")
- **Plans** board layouts for entire teaching scenarios before drawing the first element
- **Detects** when the board is crowded and suggests scrolling or cleanup
- **Reserves** space for upcoming content based on the lesson plan
- **Verifies** (asynchronously) that the board looks good after rendering
- **Never** does pixel math — expresses pedagogical intent, the solver does geometry

The board goes from a dropdown menu of 9 zones to a spatial canvas the agent controls like a teacher controls their whiteboard.
