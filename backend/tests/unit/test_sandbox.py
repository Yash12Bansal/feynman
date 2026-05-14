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
