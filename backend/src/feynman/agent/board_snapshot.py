# TODO(DEADCODE): file unused in active pipelines (precompute-gen / lecture-playback / ask-feynman) — interactive live-teaching subsystem (parked). See docs/engineering/13-redundant-code-audit.md Group 2. Safe to delete.
# """ASCII board snapshot for LLM prompt context.

# Renders the board as a 2D ASCII representation so the LLM can "see"
# where elements are, how much space they occupy, and what's empty.
# Replaces flat text summaries with genuine spatial intuition.

# Used by prompt assembly when the SpatialSolver has bounds data.
# """

# from __future__ import annotations

# from feynman.agent.board_flow import (
#     advise_scroll,
#     analyze_flow,
#     reserve_for_upcoming,
#     suggest_cleanup,
# )
# from feynman.agent.board_graph import BoardGraph
# from feynman.agent.spatial_solver import (
#     BOARD_HEIGHT,
#     BOARD_WIDTH,
#     Rect,
#     SpatialSolver,
# )

# # ASCII canvas dimensions (characters).
# CANVAS_COLS = 72
# CANVAS_ROWS = 18

# # Margins for the box border.
# BORDER = 1

# # Scale factors: board pixels → ASCII chars.
# _SCALE_X = (CANVAS_COLS - 2 * BORDER) / BOARD_WIDTH
# _SCALE_Y = (CANVAS_ROWS - 2 * BORDER) / BOARD_HEIGHT


# def generate_snapshot(
#     solver: SpatialSolver,
#     board_elements: dict[str, object],
#     *,
#     max_label_len: int = 20,
# ) -> str:
#     """Generate a 2D ASCII representation of the board.

#     The LLM sees this instead of a flat list. Provides genuine spatial
#     intuition: where things are, how much space they take, what's empty.
#     """
#     canvas: list[list[str]] = [[" "] * CANVAS_COLS for _ in range(CANVAS_ROWS)]

#     _draw_border(canvas)

#     for eid, occ_rect in solver.occupied.items():
#         el = board_elements.get(eid)
#         label = _get_label(el, eid, max_label_len)
#         type_tag = _get_type_tag(el)
#         size_tag = _get_size_tag(occ_rect)
#         _draw_element(canvas, occ_rect, label, type_tag, size_tag)

#     _label_empty_regions(canvas, solver)

#     return "\n".join("".join(row) for row in canvas)


# def generate_board_context(
#     solver: SpatialSolver,
#     board_elements: dict[str, object],
#     teaching_scenario: str = "",
#     *,
#     board_graph: BoardGraph | None = None,
#     current_concept_index: int | None = None,
#     upcoming_concepts: list[tuple[str, str | None]] | None = None,
# ) -> str:
#     """Full board context for LLM prompt: snapshot + metrics + suggestions.

#     This replaces BoardState.summary() as the primary board context
#     in the teaching prompt when spatial data is available.
#     """
#     parts: list[str] = []

#     # ASCII snapshot.
#     snapshot = generate_snapshot(solver, board_elements)
#     parts.append(snapshot)

#     # Metrics line.
#     free_pct = solver.free_space_percentage()
#     density = solver.density_by_quadrant()
#     busy = [name for name, pct in density.items() if pct > 0.4]
#     open_q = [name for name, pct in density.items() if pct < 0.05]

#     metrics: list[str] = [f"Board: {free_pct:.0%} free"]
#     if busy:
#         metrics.append(f"Busy: {', '.join(busy)}")
#     if open_q:
#         metrics.append(f"Open: {', '.join(open_q)}")
#     parts.append(". ".join(metrics) + ".")

#     # Reading flow.
#     flow = solver.reading_order()
#     if flow:
#         flow_labels = []
#         for eid in flow[:6]:
#             el = board_elements.get(eid)
#             label = _get_label(el, eid, 15)
#             flow_labels.append(f"{eid}({label})")
#         parts.append(f"Reading flow: {' -> '.join(flow_labels)}")

#     # Largest free region.
#     largest = solver.largest_free_region()
#     if largest:
#         parts.append(
#             f"Largest free area: {largest.width:.0f}x{largest.height:.0f}px "
#             f"at ({largest.x:.0f},{largest.y:.0f})"
#         )

#     # Flow analysis.
#     if solver.occupied:
#         fa = analyze_flow(solver)
#         crowding_str = f" Crowding: {', '.join(fa.crowding_zones)}." if fa.crowding_zones else ""
#         parts.append(
#             f"Flow: {fa.reading_direction.replace('_', '-')}. "
#             f"Weight center: ({fa.weight_center[0]}, {fa.weight_center[1]}).{crowding_str}"
#         )

#     # Scroll advice.
#     scroll = advise_scroll(solver, board_elements)
#     if scroll:
#         parts.append(
#             f"**Scroll recommended** (urgency: {scroll.urgency}): {scroll.reason}"
#         )

#     # Cleanup suggestions.
#     if board_graph is not None and current_concept_index is not None:
#         cleanup = suggest_cleanup(board_elements, board_graph, current_concept_index)
#         if cleanup:
#             parts.append("")
#             parts.append("Cleanup candidates (safe to erase):")
#             for c in cleanup:
#                 parts.append(f"  - {c.element_id}: {c.reason}")

#     # Upcoming space reservations.
#     if upcoming_concepts:
#         reservations = reserve_for_upcoming(solver, upcoming_concepts)
#         for r in reservations:
#             parts.append(
#                 f"Reserved space needed: ~{r.estimated_width}x{r.estimated_height}px "
#                 f"({r.suggested_zone}) for '{r.concept_title}'"
#             )

#     # Placement suggestions.
#     suggestions = _compute_suggestions(solver, board_elements, teaching_scenario)
#     if suggestions:
#         parts.append("")
#         parts.append("Suggested next placements:")
#         for i, s in enumerate(suggestions[:3]):
#             parts.append(f"  {i + 1}. {s}")

#     return "\n".join(parts)


# # ── Internal helpers ─────────────────────────────────────────


# def _draw_border(canvas: list[list[str]]) -> None:
#     """Draw box border on the canvas."""
#     rows, cols = len(canvas), len(canvas[0])
#     for c in range(cols):
#         canvas[0][c] = "─"
#         canvas[rows - 1][c] = "─"
#     for r in range(rows):
#         canvas[r][0] = "│"
#         canvas[r][cols - 1] = "│"
#     canvas[0][0] = "┌"
#     canvas[0][cols - 1] = "┐"
#     canvas[rows - 1][0] = "└"
#     canvas[rows - 1][cols - 1] = "┘"


# def _draw_element(
#     canvas: list[list[str]],
#     rect: Rect,
#     label: str,
#     type_tag: str,
#     size_tag: str,
# ) -> None:
#     """Draw a labeled element on the ASCII canvas."""
#     c1 = int(rect.x * _SCALE_X) + BORDER
#     r1 = int(rect.y * _SCALE_Y) + BORDER
#     c2 = int(rect.right * _SCALE_X) + BORDER
#     r2 = int(rect.bottom * _SCALE_Y) + BORDER

#     rows, cols = len(canvas), len(canvas[0])
#     c1 = max(BORDER, min(c1, cols - BORDER - 1))
#     r1 = max(BORDER, min(r1, rows - BORDER - 1))
#     c2 = max(c1 + 2, min(c2, cols - BORDER - 1))
#     r2 = max(r1 + 1, min(r2, rows - BORDER - 1))

#     el_width = c2 - c1
#     el_height = r2 - r1

#     if el_width >= 6 and el_height >= 3:
#         _draw_box(canvas, r1, c1, r2, c2)
#         _write_text(canvas, r1 + 1, c1 + 2, label[: el_width - 4])
#         if el_height >= 4:
#             tag = f"({type_tag}, {size_tag})"
#             _write_text(canvas, r1 + 2, c1 + 2, tag[: el_width - 4])
#     else:
#         _write_text(canvas, r1, c1, f"* {label[: el_width + 8]}")
#         if r1 + 1 < rows - BORDER:
#             tag = f"  ({type_tag}, {size_tag})"
#             _write_text(canvas, r1 + 1, c1, tag[: el_width + 8])


# def _draw_box(
#     canvas: list[list[str]], r1: int, c1: int, r2: int, c2: int
# ) -> None:
#     """Draw a rectangle outline on the canvas."""
#     for c in range(c1, c2 + 1):
#         if 0 <= r1 < len(canvas) and 0 <= c < len(canvas[0]):
#             canvas[r1][c] = "─"
#         if 0 <= r2 < len(canvas) and 0 <= c < len(canvas[0]):
#             canvas[r2][c] = "─"
#     for r in range(r1, r2 + 1):
#         if 0 <= r < len(canvas) and 0 <= c1 < len(canvas[0]):
#             canvas[r][c1] = "│"
#         if 0 <= r < len(canvas) and 0 <= c2 < len(canvas[0]):
#             canvas[r][c2] = "│"
#     if 0 <= r1 < len(canvas) and 0 <= c1 < len(canvas[0]):
#         canvas[r1][c1] = "┌"
#     if 0 <= r1 < len(canvas) and 0 <= c2 < len(canvas[0]):
#         canvas[r1][c2] = "┐"
#     if 0 <= r2 < len(canvas) and 0 <= c1 < len(canvas[0]):
#         canvas[r2][c1] = "└"
#     if 0 <= r2 < len(canvas) and 0 <= c2 < len(canvas[0]):
#         canvas[r2][c2] = "┘"


# def _write_text(canvas: list[list[str]], row: int, col: int, text: str) -> None:
#     """Write text onto the canvas at a position (clamped to border)."""
#     if row < 0 or row >= len(canvas):
#         return
#     for i, ch in enumerate(text):
#         c = col + i
#         if BORDER <= c < len(canvas[0]) - BORDER:
#             canvas[row][c] = ch


# def _label_empty_regions(canvas: list[list[str]], solver: SpatialSolver) -> None:
#     """Write '(empty)' in large empty areas of the canvas."""
#     largest = solver.largest_free_region()
#     if not largest or largest.area < 100_000:
#         return
#     cr = int(largest.center_y * _SCALE_Y) + BORDER
#     cc = int(largest.center_x * _SCALE_X) + BORDER
#     _write_text(canvas, cr, cc - 3, "(empty)")


# def _get_label(el: object | None, eid: str, max_len: int) -> str:
#     if el is None:
#         return eid
#     label = getattr(el, "label", "") or eid
#     return label[:max_len]


# def _get_type_tag(el: object | None) -> str:
#     if el is None:
#         return "?"
#     t = getattr(el, "type", "")
#     short = {
#         "show_text": "txt",
#         "show_equation": "eq",
#         "draw_diagram": "diag",
#         "draw_design_diagram": "design",
#         "draw_scene": "scene",
#         "step_equation": "steps",
#         "show_graph": "graph",
#     }
#     return short.get(t, t[:6])


# def _get_size_tag(rect: Rect) -> str:
#     area = rect.area
#     board_area = BOARD_WIDTH * BOARD_HEIGHT
#     ratio = area / board_area
#     if ratio > 0.08:
#         return "lg"
#     if ratio > 0.02:
#         return "md"
#     return "sm"


# def _compute_suggestions(
#     solver: SpatialSolver,
#     board_elements: dict[str, object],
#     teaching_scenario: str,
# ) -> list[str]:
#     """Generate 2-3 suggested placements based on board state."""
#     suggestions: list[str] = []

#     # Find the most recent anchor (diagram/scene) for relational suggestions.
#     latest_anchor_id: str | None = None
#     latest_anchor_step = -1
#     for eid, el in board_elements.items():
#         el_type = getattr(el, "type", "")
#         step = getattr(el, "created_at", 0)
#         if (
#             el_type in ("draw_design_diagram", "draw_scene", "draw_diagram")
#             and step > latest_anchor_step
#         ):
#             latest_anchor_id = eid
#             latest_anchor_step = step

#     occupied = solver.occupied

#     # Suggestion 1: Near the latest anchor.
#     if latest_anchor_id and latest_anchor_id in occupied:
#         anchor_rect = occupied[latest_anchor_id]
#         right_space = BOARD_WIDTH - anchor_rect.right
#         if right_space > 200:
#             suggestions.append(
#                 f'Supporting content -> near="{latest_anchor_id}", '
#                 f'relation="right_of" ({right_space:.0f}px available)'
#             )
#         below_space = BOARD_HEIGHT - anchor_rect.bottom
#         if below_space > 150:
#             suggestions.append(
#                 f'Follow-up content -> near="{latest_anchor_id}", '
#                 f'relation="below" ({below_space:.0f}px available)'
#             )

#     # Suggestion 2: Largest free region for new cluster.
#     largest = solver.largest_free_region()
#     if largest and largest.area > 200_000:
#         zone = SpatialSolver._nearest_zone(largest.center_x, largest.center_y)
#         suggestions.append(
#             f'New concept cluster -> zone="{zone}" '
#             f"({largest.width:.0f}x{largest.height:.0f}px free)"
#         )

#     return suggestions
