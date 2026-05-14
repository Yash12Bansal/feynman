"""Tests for the diagram-Python sandbox (Phase 3-1).

Verifies AST whitelist rejection, restricted builtins, happy-path
execution, and timeout enforcement.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from feynman.visuals.canvas_dsl import Canvas
from feynman.visuals.sandbox import SandboxError, execute_python_diagram

# ── Happy paths ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_minimal_happy_path() -> None:
    code = "canvas.add_circle(center=(450, 325), radius=80, role='moon')"
    canvas = await execute_python_diagram(code)
    assert isinstance(canvas, Canvas)
    spec = canvas.export()
    assert spec["elements"][0]["type"] == "svg_circle"
    assert spec["dictionary"][spec["elements"][0]["id"]]["role"] == "moon"


@pytest.mark.asyncio
async def test_math_module_is_available() -> None:
    code = (
        "import_substitute = None\n"  # not an import statement
        "theta = math.radians(30)\n"
        "x = 100 + 200 * math.cos(theta)\n"
        "y = 100 + 200 * math.sin(theta)\n"
        "canvas.add_line(start=(100, 100), end=(x, y))\n"
    )
    canvas = await execute_python_diagram(code)
    line = canvas.export()["elements"][0]
    # 200 * cos(30°) = 173.20508...
    assert abs(line["x2"] - (100 + 200 * 0.8660254)) < 0.001


@pytest.mark.asyncio
async def test_caller_can_rebind_canvas_to_new_instance() -> None:
    code = (
        "canvas = Canvas(width=1024, title='Rebind')\ncanvas.add_line(start=(0, 0), end=(10, 10))\n"
    )
    canvas = await execute_python_diagram(code)
    assert canvas.export()["width"] == 1024
    assert canvas.export()["title"] == "Rebind"


@pytest.mark.asyncio
async def test_for_loop_and_list_comprehension() -> None:
    code = "for i in range(5):\n    canvas.add_circle(center=(100 * i, 100), radius=10)\n"
    canvas = await execute_python_diagram(code)
    assert len(canvas.export()["elements"]) == 5


@pytest.mark.asyncio
async def test_phase_3_2_arc_latex_group_round_trip() -> None:
    """End-to-end: angle marker (arc) + KaTeX label inside a translated group."""
    code = (
        'g = canvas.add_group(transform="translate(100, 50)", role="angle_block")\n'
        "g.add_arc(center=(0, 0), radius=40, start_angle_deg=0, end_angle_deg=-60, "
        'role="theta_arc")\n'
        'g.add_latex(position=(20, -10), expression=r"\\theta", role="theta_label")\n'
    )
    canvas = await execute_python_diagram(code)
    spec = canvas.export()
    assert len(spec["elements"]) == 1
    grp = spec["elements"][0]
    assert grp["type"] == "svg_group"
    assert grp["transform"] == "translate(100, 50)"
    assert grp["elements"][0]["type"] == "svg_arc"
    assert grp["elements"][1]["type"] == "svg_latex"
    # Backslash in r"\theta" survives intact across the sandbox + DSL boundary
    assert grp["elements"][1]["expression"] == r"\theta"
    # Children registered in flat top-level dictionary
    assert "theta_arc" in {v["role"] for v in spec["dictionary"].values()}
    assert "theta_label" in {v["role"] for v in spec["dictionary"].values()}


@pytest.mark.asyncio
async def test_phase_3_2_graph_with_js_math_curves() -> None:
    """Graph curve expressions pass through verbatim (evaluated client-side as JS)."""
    code = (
        "g = canvas.add_graph(position=(50, 50), width=400, height=200, "
        "x_domain=(-3.14, 3.14), y_domain=(-1.5, 1.5))\n"
        'g.add_curve(expression="sin(x)", color="#7fd4ff")\n'
        'g.add_curve(expression="cos(x)", color="#ff7fc6")\n'
    )
    canvas = await execute_python_diagram(code)
    g = canvas.export()["elements"][0]
    assert g["type"] == "graph"
    assert [c["expression"] for c in g["curves"]] == ["sin(x)", "cos(x)"]


# ── Whitelist enforcement ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_import_statement_is_rejected() -> None:
    with pytest.raises(SandboxError, match="Import"):
        await execute_python_diagram("import os")


@pytest.mark.asyncio
async def test_import_from_statement_is_rejected() -> None:
    with pytest.raises(SandboxError, match="ImportFrom"):
        await execute_python_diagram("from os import system")


@pytest.mark.asyncio
async def test_try_block_is_rejected() -> None:
    """Try blocks would let sandbox code swallow our SandboxError."""
    with pytest.raises(SandboxError, match="Try"):
        await execute_python_diagram("try:\n    canvas.foo()\nexcept Exception:\n    pass")


@pytest.mark.asyncio
async def test_dunder_attribute_access_is_rejected() -> None:
    with pytest.raises(SandboxError, match="private/dunder"):
        await execute_python_diagram("x = canvas.__class__")


@pytest.mark.asyncio
async def test_getattr_is_rejected() -> None:
    with pytest.raises(SandboxError, match="Disallowed name"):
        await execute_python_diagram("x = getattr(canvas, 'add_line')")


@pytest.mark.asyncio
async def test_eval_is_rejected() -> None:
    with pytest.raises(SandboxError, match="Disallowed name"):
        await execute_python_diagram("x = eval('1+1')")


@pytest.mark.asyncio
async def test_open_is_rejected() -> None:
    with pytest.raises(SandboxError, match="Disallowed name"):
        await execute_python_diagram("f = open('/etc/passwd')")


# ── Execution error surfacing ────────────────────────────────────


@pytest.mark.asyncio
async def test_runtime_error_in_user_code_surfaces_as_sandbox_error() -> None:
    with pytest.raises(SandboxError, match="ZeroDivisionError"):
        await execute_python_diagram("x = 1 / 0")


@pytest.mark.asyncio
async def test_syntax_error_surfaces_as_sandbox_error() -> None:
    with pytest.raises(SandboxError, match="syntax error"):
        await execute_python_diagram("def )(:")


@pytest.mark.asyncio
async def test_calling_unknown_canvas_method_raises_sandbox_error() -> None:
    with pytest.raises(SandboxError, match="AttributeError"):
        await execute_python_diagram("canvas.add_dragon(fire=True)")


# ── Timeout ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_timeout_raises_sandbox_error() -> None:
    """Timeout path raises ``SandboxError``.

    We mock ``asyncio.wait_for`` rather than burning real wall-clock time
    on a tight loop — a tight loop that exceeds the deadline also leaks
    its thread (sandbox module docstring), so testing it for real either
    runs too long or blocks pytest's executor shutdown.
    """

    async def _raise_timeout(coro, **_kwargs):
        # Close the to_thread coroutine so we don't leak a never-awaited warning.
        coro.close()
        raise TimeoutError("synthetic deadline")

    with (
        patch("feynman.visuals.sandbox.asyncio.wait_for", side_effect=_raise_timeout),
        pytest.raises(SandboxError, match="timeout"),
    ):
        await execute_python_diagram(
            "canvas.add_circle(center=(0, 0), radius=10)",
            timeout=0.2,
        )


# ── Phase 3-3: geometric helpers reachable as bare names ──────────


@pytest.mark.asyncio
async def test_phase_3_3_helpers_available_as_bare_names_in_sandbox() -> None:
    """`midpoint`, `polar`, `perpendicular_to` etc. are in scope without import."""
    code = (
        "hit = polar((0, 0), 100, 0)\n"  # 0° = right edge, so hit == (100, 0)
        "mid = midpoint((0, 0), (10, 10))\n"
        "tip = perpendicular_to((0, 0), (10, 0), base=(5, 0), length=5)\n"
        "canvas.add_circle(center=hit, radius=2, role='hit_marker')\n"
        "canvas.add_text(position=mid, text='midpoint', role='mid_label')\n"
        "canvas.add_arrow(start=(5, 0), end=tip, role='normal')\n"
    )
    canvas = await execute_python_diagram(code)
    spec = canvas.export()
    # Three elements landed cleanly — no NameError on the bare-name helpers.
    assert len(spec["elements"]) == 3
    # polar(0,0)→100,0 routes through correctly
    hit_marker = spec["elements"][0]
    assert hit_marker["cx"] == 100.0 and hit_marker["cy"] == 0.0


@pytest.mark.asyncio
async def test_phase_3_3_done_criterion_ramp_at_35_degrees_with_perpendicular_normal_force() -> (
    None
):
    """Done criterion: agent draws 35° ramp + normal force perpendicular to surface,
    measured to ±0.5° on the rendered spec."""
    import math as _m

    code = (
        "theta_deg = 35\n"
        "ramp_left = (150, 500)\n"
        "ramp_right = polar(ramp_left, 400, -theta_deg)\n"
        "ramp = canvas.add_line(start=ramp_left, end=ramp_right, role='incline')\n"
        "block = canvas.add_rect(\n"
        "    top_left=(ramp.midpoint[0] - 25, ramp.midpoint[1] - 50),\n"
        "    width=50, height=50, role='block',\n"
        ")\n"
        "N_tip = perpendicular_to(ramp_left, ramp_right, base=block.center, "
        "length=80, side='left')\n"
        "canvas.add_arrow(start=block.center, end=N_tip, role='normal_force')\n"
    )
    canvas = await execute_python_diagram(code)
    spec = canvas.export()

    line = next(e for e in spec["elements"] if e["type"] == "svg_line")
    arrow = next(e for e in spec["elements"] if e["type"] == "svg_arrow")

    # Ramp angle, from the rendered coords. atan2(-dy, dx) flips the screen-y-down
    # convention back to "above-horizon" degrees.
    dx = line["x2"] - line["x1"]
    dy = line["y2"] - line["y1"]
    measured_deg = _m.degrees(_m.atan2(-dy, dx))
    assert measured_deg == pytest.approx(35.0, abs=0.5)

    # Normal force orthogonality on the rendered arrow vs the rendered ramp line.
    arr_dx = arrow["x2"] - arrow["x1"]
    arr_dy = arrow["y2"] - arrow["y1"]
    assert arr_dx * dx + arr_dy * dy == pytest.approx(0.0, abs=1e-6)


@pytest.mark.asyncio
async def test_phase_3_3_intersect_failure_surfaces_as_sandbox_error() -> None:
    """Parallel-line failure inside the sandbox surfaces with a clear message."""
    code = "p = intersect(((0,0),(10,0)), ((0,5),(10,5)))\n"
    with pytest.raises(SandboxError, match="parallel"):
        await execute_python_diagram(code)
