"""Tests for the Phase 3-4 mode-dispatch heuristic.

`_dispatch_mode` is called when the LLM passes `mode="auto"` (the new
default on `draw_design_diagram`). The heuristic scans the prompt for
strong geometric keywords and escalates to the Python-DSL path when
they're present; otherwise stays on direct-JSON.
"""

from __future__ import annotations

from feynman.agent.design_bridge import _dispatch_mode

# ── Python triggers ──────────────────────────────────────────────


def test_dispatch_mode_perpendicular_keyword_routes_to_python() -> None:
    assert (
        _dispatch_mode("Draw a ramp with a normal force perpendicular to the surface") == "python"
    )


def test_dispatch_mode_tangent_keyword_routes_to_python() -> None:
    assert _dispatch_mode("Draw a circle and a line tangent to it from (100, 50)") == "python"


def test_dispatch_mode_exact_angle_keyword_routes_to_python() -> None:
    assert _dispatch_mode("Draw a ramp at an exact angle of 35 degrees") == "python"


def test_dispatch_mode_exactly_degrees_routes_to_python() -> None:
    assert _dispatch_mode("Show a wedge tilted exactly 22°") == "python"


def test_dispatch_mode_intersection_keyword_routes_to_python() -> None:
    assert _dispatch_mode("Two lines crossing — mark their intersection") == "python"


def test_dispatch_mode_parallel_to_routes_to_python() -> None:
    assert _dispatch_mode("Draw a line parallel to the x-axis at y=100") == "python"


def test_dispatch_mode_normal_force_routes_to_python() -> None:
    assert _dispatch_mode("FBD of a block on a slope — show the normal force") == "python"


def test_dispatch_mode_perpendicular_bisector_routes_to_python() -> None:
    assert _dispatch_mode("Construct the perpendicular bisector of segment AB") == "python"


# ── Stays direct ────────────────────────────────────────────────


def test_dispatch_mode_simple_stock_topology_stays_direct() -> None:
    """No geometric keywords → cheaper direct-JSON path."""
    assert (
        _dispatch_mode("Draw a right triangle labelled with adjacent, opposite, hypotenuse")
        == "direct"
    )


def test_dispatch_mode_cell_diagram_stays_direct() -> None:
    assert _dispatch_mode("Draw a plant cell with chloroplasts and mitochondria") == "direct"


def test_dispatch_mode_periodic_table_stays_direct() -> None:
    assert _dispatch_mode("Show the alkali metals column from the periodic table") == "direct"


def test_dispatch_mode_two_perpendicular_axes_routes_to_python() -> None:
    """Even informal uses of `perpendicular` escalate — false-positive accepted.

    This documents the conservative-for-precision tradeoff: ~100-200ms extra
    latency on the Python path is the cost of catching diagrams that DO need
    exactness. Tighten the keyword list later if observed too noisy.
    """
    assert _dispatch_mode("Draw two perpendicular axes meeting at the origin") == "python"


# ── Case-insensitivity ──────────────────────────────────────────


def test_dispatch_mode_is_case_insensitive() -> None:
    assert _dispatch_mode("PERPENDICULAR to the floor") == "python"
    assert _dispatch_mode("Tangent To this circle") == "python"
