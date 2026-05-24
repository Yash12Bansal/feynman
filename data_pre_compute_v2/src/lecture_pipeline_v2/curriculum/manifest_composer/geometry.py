"""Axis-aligned Rect primitive for layout planning.

Doc 18 simplification: the old annotation-positioning helpers
(`pin_label_rect`, `callout_bubble_rect`, `bracket_label_rect`,
`resolve_pin_position`, `resolve_callout_direction`, the fallback tables)
were deleted along with the 5-marker annotation system. Only `Rect` survives
because `policies/layout.py` uses it for page-coord block/diagram bounds.

Rect pattern adapted verbatim from
`backend/src/feynman/agent/spatial_solver.py:15`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    """Axis-aligned rectangle in viewBox or page-coord units."""

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

    def overlaps(self, other: Rect) -> bool:
        return (
            self.x < other.right
            and self.right > other.x
            and self.y < other.bottom
            and self.bottom > other.y
        )

    def padded(self, amount: float) -> Rect:
        return Rect(
            x=self.x - amount,
            y=self.y - amount,
            width=self.width + amount * 2,
            height=self.height + amount * 2,
        )
