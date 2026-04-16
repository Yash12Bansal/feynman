"""MaxRects-based spatial solver for the teaching board.

Tracks occupied rectangles, computes free space, and finds optimal
placement positions. All methods are synchronous and sub-millisecond.

Used by the Board Cortex to answer: "Where should this go? Will it fit?"
"""

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
            self.x < other.right
            and self.right > other.x
            and self.y < other.bottom
            and self.bottom > other.y
        )

    def contains(self, other: Rect) -> bool:
        return (
            self.x <= other.x
            and self.right >= other.right
            and self.y <= other.y
            and self.bottom >= other.bottom
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

    def __init__(
        self, width: float = BOARD_WIDTH, height: float = BOARD_HEIGHT
    ) -> None:
        self._width = width
        self._height = height
        self._occupied: dict[str, Rect] = {}
        # MaxRects: list of maximal free rectangles
        self._free_rects: list[Rect] = [Rect(0, 0, width, height)]

    @property
    def width(self) -> float:
        """Board width in pixels."""
        return self._width

    @property
    def height(self) -> float:
        """Board height in pixels."""
        return self._height

    @property
    def occupied(self) -> dict[str, Rect]:
        """Read-only view of occupied elements."""
        return dict(self._occupied)

    @property
    def free_rects(self) -> list[Rect]:
        """Current maximal free rectangles."""
        return list(self._free_rects)

    def is_area_free(self, rect: Rect, padding: float = 0) -> bool:
        """Check if a rectangular area has no occupied elements."""
        return not self._overlaps_any(rect, padding=padding)

    # ── Mutations ────────────────────────────────────────────

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

    # ── Queries ──────────────────────────────────────────────

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
        return max(0.0, 1.0 - used / (self._width * self._height))

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
        # Strategy 1: Place relative to anchor
        if anchor_id and anchor_id in self._occupied:
            result = self._place_near_anchor(
                width, height, self._occupied[anchor_id], relation, padding,
                anchor_id=anchor_id,
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
        """Element IDs sorted by visual reading flow (L->R, T->B).

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

    # ── Internals ────────────────────────────────────────────

    def _place_near_anchor(
        self,
        w: float,
        h: float,
        anchor: Rect,
        relation: SpatialRelation,
        padding: float,
        anchor_id: str | None = None,
    ) -> PlacementResult | None:
        """Try to place adjacent to an anchor element."""
        candidates: list[tuple[float, float, str]] = []

        if relation == SpatialRelation.RIGHT_OF:
            candidates = [
                (anchor.right + padding, anchor.y, "right of anchor"),
                (
                    anchor.right + padding,
                    anchor.center_y - h / 2,
                    "right, vertically centered",
                ),
            ]
        elif relation == SpatialRelation.LEFT_OF:
            candidates = [
                (anchor.x - w - padding, anchor.y, "left of anchor"),
            ]
        elif relation == SpatialRelation.BELOW:
            candidates = [
                (anchor.x, anchor.bottom + padding, "below anchor"),
                (
                    anchor.center_x - w / 2,
                    anchor.bottom + padding,
                    "below, centered",
                ),
            ]
        elif relation == SpatialRelation.ABOVE:
            candidates = [
                (anchor.x, anchor.y - h - padding, "above anchor"),
            ]
        elif relation == SpatialRelation.CENTERED:
            candidates = [
                (
                    anchor.center_x - w / 2,
                    anchor.center_y - h / 2,
                    "centered on anchor",
                ),
            ]

        # CENTERED intentionally overlaps the anchor (overlay use case)
        exclude = {anchor_id} if anchor_id and relation == SpatialRelation.CENTERED else set()

        for cx, cy, reason in candidates:
            candidate = Rect(cx, cy, w, h)
            # Check: within board bounds
            if cx < 0 or cy < 0 or cx + w > self._width or cy + h > self._height:
                continue
            # Check: doesn't overlap any occupied rect (with padding)
            if self._overlaps_any(candidate, padding=padding / 2, exclude=exclude):
                continue
            return PlacementResult(
                x=cx,
                y=cy,
                width=w,
                height=h,
                confidence=0.9,
                reason=reason,
                zone_hint=self._nearest_zone(cx + w / 2, cy + h / 2),
            )
        return None

    def _place_best_fit(
        self,
        w: float,
        h: float,
        padding: float,
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
            x=x,
            y=y,
            width=w,
            height=h,
            confidence=0.7,
            reason="best-fit free region",
            zone_hint=self._nearest_zone(x + w / 2, y + h / 2),
        )

    def _overlaps_any(
        self, rect: Rect, padding: float = 0, exclude: set[str] | None = None,
    ) -> bool:
        """Check if rect overlaps any occupied element (with optional padding)."""
        padded = Rect(
            rect.x - padding,
            rect.y - padding,
            rect.width + padding * 2,
            rect.height + padding * 2,
        )
        for eid, occ in self._occupied.items():
            if exclude and eid in exclude:
                continue
            if padded.overlaps(occ):
                return True
        return False

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
                    new_free.append(
                        Rect(occ.right, fr.y, fr.right - occ.right, fr.height)
                    )
                # Top remainder
                if occ.y > fr.y:
                    new_free.append(Rect(fr.x, fr.y, fr.width, occ.y - fr.y))
                # Bottom remainder
                if occ.bottom < fr.bottom:
                    new_free.append(
                        Rect(fr.x, occ.bottom, fr.width, fr.bottom - occ.bottom)
                    )
            free = new_free

        # Remove rects contained within others
        pruned: list[Rect] = []
        for i, a in enumerate(free):
            contained = False
            for j, b in enumerate(free):
                if i != j and b.contains(a) and a != b:
                    contained = True
                    break
            if (
                not contained
                and a.width >= MIN_USEFUL_SIZE
                and a.height >= MIN_USEFUL_SIZE
            ):
                pruned.append(a)

        self._free_rects = pruned

    @staticmethod
    def _nearest_zone(cx: float, cy: float) -> str:
        """Map center point to nearest zone name for backward compat."""
        col = "left" if cx < 640 else ("center" if cx < 1280 else "right")
        row = "top" if cy < 360 else ("center" if cy < 720 else "bottom")
        return f"{row}-{col}"
