# TODO(DEADCODE): file unused in active pipelines (precompute-gen / lecture-playback / ask-feynman) — interactive live-teaching subsystem (parked). See docs/engineering/13-redundant-code-audit.md Group 2. Safe to delete.
# """Scene graph — pixel-precise spatial model of the board.

# Closes the feedback loop: frontend reports rendered element bounds → SceneGraph
# indexes them → provides rich spatial context for LLM prompts (positions, sizes,
# relationships, density, free regions).

# Design:
# - One SceneGraph per board.
# - update_bounds() replaces all bounds atomically (full snapshot from frontend).
# - All queries are O(n) or O(n²) on element count — fine for ~20 elements per board.
# - summary() returns natural language; returns "" when no bounds → enables graceful fallback.
# """

# from __future__ import annotations

# import math
# from dataclasses import dataclass, field
# from enum import StrEnum

# from pydantic import BaseModel

# # Board dimensions must match frontend constants.
# BOARD_WIDTH = 1920
# BOARD_HEIGHT = 1080


# # ── Data structures ───────────────────────────────────────────


# class SpatialRelation(StrEnum):
#     ABOVE = "above"
#     BELOW = "below"
#     LEFT_OF = "left_of"
#     RIGHT_OF = "right_of"
#     OVERLAPPING = "overlapping"


# @dataclass(frozen=True)
# class ElementBounds:
#     """Pixel-precise bounds of a rendered element in board space."""

#     element_id: str
#     x: float
#     y: float
#     width: float
#     height: float

#     @property
#     def center_x(self) -> float:
#         return self.x + self.width / 2

#     @property
#     def center_y(self) -> float:
#         return self.y + self.height / 2

#     @property
#     def right(self) -> float:
#         return self.x + self.width

#     @property
#     def bottom(self) -> float:
#         return self.y + self.height

#     @property
#     def area(self) -> float:
#         return self.width * self.height

#     def overlaps(self, other: ElementBounds) -> bool:
#         """True if the two bounding boxes overlap."""
#         return (
#             self.x < other.right
#             and self.right > other.x
#             and self.y < other.bottom
#             and self.bottom > other.y
#         )


# @dataclass
# class FreeRegion:
#     """A rectangular free-space region on the board."""

#     x: float
#     y: float
#     width: float
#     height: float

#     @property
#     def area(self) -> float:
#         return self.width * self.height


# class BoundsReportElement(BaseModel):
#     """A single element's bounds from the frontend report."""

#     element_id: str
#     x: float
#     y: float
#     width: float
#     height: float


# class BoundsReportPayload(BaseModel):
#     """Wire format from frontend BoundsReporter."""

#     type: str = "bounds_report"
#     board_id: str
#     timestamp: int = 0
#     elements: list[BoundsReportElement] = []


# # ── Size classification ───────────────────────────────────────

# _BOARD_AREA = BOARD_WIDTH * BOARD_HEIGHT


# def _size_label(area: float) -> str:
#     """Classify element size relative to board area."""
#     ratio = area / _BOARD_AREA
#     if ratio > 0.08:
#         return "large"
#     if ratio > 0.02:
#         return "medium"
#     return "small"


# def _position_label(cx: float, cy: float) -> str:
#     """Approximate position label from center coordinates."""
#     if cy < BOARD_HEIGHT / 3:
#         v = "top"
#     elif cy < 2 * BOARD_HEIGHT / 3:
#         v = "middle"
#     else:
#         v = "bottom"

#     if cx < BOARD_WIDTH / 3:
#         h = "left"
#     elif cx < 2 * BOARD_WIDTH / 3:
#         h = "center"
#     else:
#         h = "right"

#     return f"{v}-{h}"


# # ── SceneGraph ────────────────────────────────────────────────


# @dataclass
# class SceneGraph:
#     """Spatial index of element bounds for a single board.

#     Updated by frontend bounds reports. Queried by BoardState.summary()
#     to enrich LLM prompts with spatial context.
#     """

#     _bounds: dict[str, ElementBounds] = field(default_factory=dict)

#     def update_bounds(self, report: BoundsReportPayload) -> None:
#         """Replace all bounds from a frontend snapshot."""
#         self._bounds.clear()
#         for el in report.elements:
#             self._bounds[el.element_id] = ElementBounds(
#                 element_id=el.element_id,
#                 x=el.x,
#                 y=el.y,
#                 width=el.width,
#                 height=el.height,
#             )

#     def get_bounds(self, element_id: str) -> ElementBounds | None:
#         return self._bounds.get(element_id)

#     def remove_element(self, element_id: str) -> None:
#         self._bounds.pop(element_id, None)

#     def clear(self) -> None:
#         self._bounds.clear()

#     @property
#     def element_count(self) -> int:
#         return len(self._bounds)

#     # ── Spatial queries ────────────────────────────────────────

#     def neighbors(self, element_id: str, max_distance: float = 300.0) -> list[ElementBounds]:
#         """Elements whose centers are within max_distance of target's center."""
#         target = self._bounds.get(element_id)
#         if target is None:
#             return []

#         result = []
#         for eb in self._bounds.values():
#             if eb.element_id == element_id:
#                 continue
#             dx = eb.center_x - target.center_x
#             dy = eb.center_y - target.center_y
#             dist = math.sqrt(dx * dx + dy * dy)
#             if dist <= max_distance:
#                 result.append(eb)
#         return result

#     def spatial_relation(self, from_id: str, to_id: str) -> SpatialRelation | None:
#         """Primary spatial relationship from one element to another.

#         Returns the dominant direction: "eq-1 is ABOVE text-2" means
#         eq-1's center is higher than text-2's center.
#         Returns None if either element is missing.
#         """
#         a = self._bounds.get(from_id)
#         b = self._bounds.get(to_id)
#         if a is None or b is None:
#             return None

#         if a.overlaps(b):
#             return SpatialRelation.OVERLAPPING

#         dx = b.center_x - a.center_x
#         dy = b.center_y - a.center_y

#         # Dominant axis
#         if abs(dy) >= abs(dx):
#             return SpatialRelation.ABOVE if dy > 0 else SpatialRelation.BELOW
#         else:
#             return SpatialRelation.LEFT_OF if dx > 0 else SpatialRelation.RIGHT_OF

#     def density_summary(self) -> dict[str, float]:
#         """Percentage of area used in each board quadrant.

#         Quadrants: top-left, top-right, bottom-left, bottom-right.
#         """
#         half_w = BOARD_WIDTH / 2
#         half_h = BOARD_HEIGHT / 2
#         quadrant_area = half_w * half_h

#         quadrants = {
#             "top-left": (0, 0, half_w, half_h),
#             "top-right": (half_w, 0, BOARD_WIDTH, half_h),
#             "bottom-left": (0, half_h, half_w, BOARD_HEIGHT),
#             "bottom-right": (half_w, half_h, BOARD_WIDTH, BOARD_HEIGHT),
#         }

#         result: dict[str, float] = {}
#         for name, (qx1, qy1, qx2, qy2) in quadrants.items():
#             used = 0.0
#             for eb in self._bounds.values():
#                 # Intersection area
#                 ix1 = max(eb.x, qx1)
#                 iy1 = max(eb.y, qy1)
#                 ix2 = min(eb.right, qx2)
#                 iy2 = min(eb.bottom, qy2)
#                 if ix2 > ix1 and iy2 > iy1:
#                     used += (ix2 - ix1) * (iy2 - iy1)
#             result[name] = min(used / quadrant_area, 1.0)
#         return result

#     def largest_free_region(self) -> FreeRegion | None:
#         """Approximate largest open rectangular area on the board.

#         Uses a candidate-sweep approach: checks regions formed by
#         the board edges and element boundaries. Not pixel-perfect
#         but good enough for LLM spatial guidance.
#         """
#         if not self._bounds:
#             return FreeRegion(x=0, y=0, width=BOARD_WIDTH, height=BOARD_HEIGHT)

#         # Collect x and y boundaries
#         xs = sorted(
#             {0.0, float(BOARD_WIDTH)}
#             | {eb.x for eb in self._bounds.values()}
#             | {eb.right for eb in self._bounds.values()}
#         )
#         ys = sorted(
#             {0.0, float(BOARD_HEIGHT)}
#             | {eb.y for eb in self._bounds.values()}
#             | {eb.bottom for eb in self._bounds.values()}
#         )

#         best: FreeRegion | None = None
#         bounds_list = list(self._bounds.values())

#         for i in range(len(xs) - 1):
#             for j in range(len(ys) - 1):
#                 rx, ry = xs[i], ys[j]
#                 rw = xs[i + 1] - rx
#                 rh = ys[j + 1] - ry

#                 if rw < 50 or rh < 50:  # Too small to be useful
#                     continue

#                 # Check if any element overlaps this cell
#                 occupied = False
#                 for eb in bounds_list:
#                     if rx < eb.right and rx + rw > eb.x and ry < eb.bottom and ry + rh > eb.y:
#                         occupied = True
#                         break

#                 if not occupied:
#                     area = rw * rh
#                     if best is None or area > best.area:
#                         best = FreeRegion(x=rx, y=ry, width=rw, height=rh)

#         return best

#     # ── LLM summary ───────────────────────────────────────────

#     def summary(self, board_elements: dict[str, object] | None = None) -> str:
#         """Generate natural-language spatial summary for LLM prompts.

#         Args:
#             board_elements: dict of element_id → BoardElement from BoardState.
#                 Used to get labels for richer descriptions. If None, uses IDs only.

#         Returns:
#             Multi-line string with positions, sizes, relationships, and open regions.
#             Returns "" when no bounds are available (enables graceful fallback).
#         """
#         if not self._bounds:
#             return ""

#         lines: list[str] = []

#         # Element descriptions with position and size
#         for eid, eb in self._bounds.items():
#             pos = _position_label(eb.center_x, eb.center_y)
#             size = _size_label(eb.area)

#             label = ""
#             if board_elements:
#                 el_obj = board_elements.get(eid)
#                 if el_obj is not None:
#                     label = getattr(el_obj, "label", "") or ""

#             if label:
#                 lines.append(f"- {eid}: {label} — {pos}, {size}")
#             else:
#                 lines.append(f"- {eid} — {pos}, {size}")

#         # Spatial relationships (only for small element counts to avoid prompt bloat)
#         bounds_list = list(self._bounds.values())
#         if 2 <= len(bounds_list) <= 10:
#             rels: list[str] = []
#             for i, a in enumerate(bounds_list):
#                 for b in bounds_list[i + 1 :]:
#                     rel = self.spatial_relation(a.element_id, b.element_id)
#                     if rel is None:
#                         continue

#                     a_label = a.element_id
#                     b_label = b.element_id
#                     if board_elements:
#                         a_obj = board_elements.get(a.element_id)
#                         b_obj = board_elements.get(b.element_id)
#                         if a_obj:
#                             a_l = getattr(a_obj, "label", "") or ""
#                             if a_l:
#                                 a_label = f"{a.element_id} ({a_l})"
#                         if b_obj:
#                             b_l = getattr(b_obj, "label", "") or ""
#                             if b_l:
#                                 b_label = f"{b.element_id} ({b_l})"

#                     rel_desc = rel.value.replace("_", " ")
#                     rels.append(f"  {a_label} is {rel_desc} {b_label}")

#             if rels:
#                 lines.append("")
#                 lines.append("Spatial relationships:")
#                 lines.extend(rels)

#         # Open regions
#         density = self.density_summary()
#         open_quadrants = [name for name, pct in density.items() if pct < 0.05]
#         if open_quadrants:
#             lines.append("")
#             lines.append(f"Open regions: {', '.join(open_quadrants)}")

#         return "\n".join(lines)
