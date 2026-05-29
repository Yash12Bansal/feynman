# TODO(DEADCODE): tests parked/dead modules (Group 1/2/3); see docs/engineering/13-redundant-code-audit.md. Safe to delete.
# """Tests for the Phase 3-4 mode-dispatch heuristic.

# `_dispatch_mode` is called when the LLM passes `mode="auto"` (the new
# default on `draw_design_diagram`). The heuristic scans the prompt for
# strong geometric keywords and escalates to the Python-DSL path when
# they're present; otherwise stays on direct-JSON.
# """

# from __future__ import annotations

# from feynman.agent.design_bridge import _dispatch_mode

# # ── Python triggers ──────────────────────────────────────────────


# def test_dispatch_mode_perpendicular_keyword_routes_to_python() -> None:
#     assert (
#         _dispatch_mode("Draw a ramp with a normal force perpendicular to the surface") == "python"
#     )


# def test_dispatch_mode_tangent_keyword_routes_to_python() -> None:
#     assert _dispatch_mode("Draw a circle and a line tangent to it from (100, 50)") == "python"


# def test_dispatch_mode_exact_angle_keyword_routes_to_python() -> None:
#     assert _dispatch_mode("Draw a ramp at an exact angle of 35 degrees") == "python"


# def test_dispatch_mode_exactly_degrees_routes_to_python() -> None:
#     assert _dispatch_mode("Show a wedge tilted exactly 22°") == "python"


# def test_dispatch_mode_intersection_keyword_routes_to_python() -> None:
#     assert _dispatch_mode("Two lines crossing — mark their intersection") == "python"


# def test_dispatch_mode_parallel_to_routes_to_python() -> None:
#     assert _dispatch_mode("Draw a line parallel to the x-axis at y=100") == "python"


# def test_dispatch_mode_normal_force_routes_to_python() -> None:
#     assert _dispatch_mode("FBD of a block on a slope — show the normal force") == "python"


# def test_dispatch_mode_perpendicular_bisector_routes_to_python() -> None:
#     assert _dispatch_mode("Construct the perpendicular bisector of segment AB") == "python"


# # ── Stays direct ────────────────────────────────────────────────


# def test_dispatch_mode_flowchart_stays_direct() -> None:
#     """No geometric keywords and no STEM-composite keywords → direct path.

#     Phase 3-5 added right-triangle/FBD/lens/Lewis as Python-path composites,
#     so those prompts route to Python. Stock direct-JSON diagrams that
#     don't match either filter stay on the cheaper path.
#     """
#     assert _dispatch_mode("Draw a flowchart with three boxes connected by arrows") == "direct"


# def test_dispatch_mode_cell_diagram_stays_direct() -> None:
#     assert _dispatch_mode("Draw a plant cell with chloroplasts and mitochondria") == "direct"


# def test_dispatch_mode_periodic_table_stays_direct() -> None:
#     assert _dispatch_mode("Show the alkali metals column from the periodic table") == "direct"


# def test_dispatch_mode_two_perpendicular_axes_routes_to_python() -> None:
#     """Even informal uses of `perpendicular` escalate — false-positive accepted.

#     This documents the conservative-for-precision tradeoff: ~100-200ms extra
#     latency on the Python path is the cost of catching diagrams that DO need
#     exactness. Tighten the keyword list later if observed too noisy.
#     """
#     assert _dispatch_mode("Draw two perpendicular axes meeting at the origin") == "python"


# # ── Case-insensitivity ──────────────────────────────────────────


# def test_dispatch_mode_is_case_insensitive() -> None:
#     assert _dispatch_mode("PERPENDICULAR to the floor") == "python"
#     assert _dispatch_mode("Tangent To this circle") == "python"


# # ── Phase 3-5: STEM composite triggers ───────────────────────────


# def test_dispatch_mode_right_triangle_routes_to_python() -> None:
#     assert _dispatch_mode("Draw a right triangle for trigonometry") == "python"


# def test_dispatch_mode_free_body_diagram_routes_to_python() -> None:
#     assert _dispatch_mode("Draw a free body diagram of a block on a ramp") == "python"


# def test_dispatch_mode_free_hyphen_body_diagram_routes_to_python() -> None:
#     assert _dispatch_mode("Show a free-body diagram with three forces") == "python"


# def test_dispatch_mode_fbd_acronym_routes_to_python() -> None:
#     assert _dispatch_mode("Quick FBD of a 5 kg crate on the floor") == "python"


# def test_dispatch_mode_ray_diagram_routes_to_python() -> None:
#     assert _dispatch_mode("Walk through a ray diagram for a convex mirror") == "python"


# def test_dispatch_mode_convex_lens_routes_to_python() -> None:
#     assert _dispatch_mode("Draw a convex lens with focal points marked") == "python"


# def test_dispatch_mode_concave_lens_routes_to_python() -> None:
#     assert _dispatch_mode("Show a concave lens cross-section") == "python"


# def test_dispatch_mode_bare_lens_routes_to_python() -> None:
#     """``lens`` alone is enough — the term is physics-specific in IGCSE."""
#     assert _dispatch_mode("Draw a lens and an object at 2F") == "python"


# def test_dispatch_mode_lewis_structure_routes_to_python() -> None:
#     assert _dispatch_mode("Draw the Lewis structure for water") == "python"


# def test_dispatch_mode_methane_routes_to_python() -> None:
#     """Named molecules in canonical Lewis-structure scope auto-route."""
#     assert _dispatch_mode("Show the Lewis structure of methane") == "python"


# def test_dispatch_mode_ammonia_routes_to_python() -> None:
#     assert _dispatch_mode("Build an ammonia molecule on the board") == "python"
