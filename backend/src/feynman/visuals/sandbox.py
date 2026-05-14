"""Restricted execution of LLM-authored Python diagram scripts.

Phase 3 (`docs/design/16-diagram-awareness-rearchitecture.md`) gives the
teaching agent an opt-in path where the LLM writes Python — using the
`canvas_dsl` library — instead of emitting a DiagramSpec JSON blob. This
module runs that Python and returns the produced `Canvas`.

## Threat model

The Python code is produced by Anthropic's Claude. Users do not write
Python directly — they write natural-language prompts that influence
Claude's output. The concern is two-fold:

1. **Accidental hangs**: an LLM writes `while True: pass` and freezes
   the worker. Mitigated by `asyncio.to_thread` + `asyncio.wait_for`.
2. **Prompt-injection-driven escape**: a user prompt induces Claude
   to emit code that reaches into the running process (filesystem,
   network, secrets in env vars, other sessions). Mitigated by AST
   whitelist + restricted builtins + no `import`.

This is "defense-in-depth where Claude is reasonably trusted," not
"hostile-user-supplies-code sandbox." Production deployment with real
multi-tenant scale would graduate to a subprocess (signal-killable) or
WASM (true isolation). For Phase 3-1 walking skeleton, this floor is
sufficient.

## Known limitations (acceptable for Phase 3-1)

- **No memory bound**: `[0] * 10**10` would OOM. Add `resource.setrlimit`
  in a later phase or move to subprocess.
- **Thread leak on timeout**: `asyncio.wait_for` returns when the deadline
  hits, but the underlying thread keeps running. The leak ends when the
  user code eventually exits (or the process restarts). Tracked for the
  subprocess-migration follow-up.
"""

from __future__ import annotations

import ast
import asyncio
import math as _math
from typing import Any

from feynman.visuals.canvas_dsl import (
    Canvas,
    intersect,
    midpoint,
    parallel_at_distance,
    perpendicular_to,
    polar,
    tangent_to,
)

EXEC_TIMEOUT_SECONDS = 2.0


class SandboxError(Exception):
    """LLM-authored sandbox code failed validation, execution, or timed out."""


# AST node classes that should never appear in sandbox code. We block
# imports outright — `math`/`canvas`/`Canvas` are injected into globals
# below — and reject error-swallowing constructs so a script can't catch
# our SandboxError and pretend nothing happened.
_FORBIDDEN_NODES: tuple[type[ast.AST], ...] = (
    ast.Import,
    ast.ImportFrom,
    ast.Global,
    ast.Nonlocal,
    ast.Try,
    ast.TryStar,
)

# Names whose mere mention is a red flag — the classic Python sandbox
# escape routes go through these.
_FORBIDDEN_NAMES: frozenset[str] = frozenset(
    {
        "__import__",
        "__builtins__",
        "open",
        "exec",
        "eval",
        "compile",
        "getattr",
        "setattr",
        "delattr",
        "globals",
        "locals",
        "vars",
        "input",
        "breakpoint",
        "help",
    }
)

# Builtins we whitelist for sandboxed code. Conspicuously absent: anything
# IO-related (`open`, `input`), reflection (`getattr`, `dir`, `type`),
# and metaclass paths (`type`, `super`).
_SAFE_BUILTINS: dict[str, Any] = {
    "range": range,
    "len": len,
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "list": list,
    "tuple": tuple,
    "dict": dict,
    "set": set,
    "True": True,
    "False": False,
    "None": None,
    "enumerate": enumerate,
    "zip": zip,
    "sum": sum,
    "any": any,
    "all": all,
    "sorted": sorted,
    "reversed": reversed,
    "isinstance": isinstance,
    # silent print — useful for the LLM to "log" its thinking without
    # actually emitting to our logs.
    "print": lambda *_args, **_kwargs: None,
}


def _validate_ast(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if isinstance(node, _FORBIDDEN_NODES):
            raise SandboxError(f"Disallowed syntax in sandbox code: {type(node).__name__}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise SandboxError(f"Access to private/dunder attribute not allowed: '{node.attr}'")
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            raise SandboxError(f"Disallowed name: '{node.id}'")


def _run_sync(code: str) -> Canvas:
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise SandboxError(f"Sandbox code has syntax error: {exc}") from exc

    _validate_ast(tree)

    try:
        compiled = compile(tree, "<sandbox>", "exec")
    except SyntaxError as exc:  # pragma: no cover — caught above, defensive
        raise SandboxError(f"Sandbox code compile failed: {exc}") from exc

    canvas = Canvas()
    globals_dict: dict[str, Any] = {
        "__builtins__": _SAFE_BUILTINS,
        "math": _math,
        "Canvas": Canvas,
        "canvas": canvas,
        # Phase 3-3 geometric helpers (bare names — match design doc).
        "midpoint": midpoint,
        "polar": polar,
        "perpendicular_to": perpendicular_to,
        "parallel_at_distance": parallel_at_distance,
        "intersect": intersect,
        "tangent_to": tangent_to,
    }
    locals_dict: dict[str, Any] = {"canvas": canvas}

    try:
        exec(compiled, globals_dict, locals_dict)
    except SandboxError:
        raise
    except Exception as exc:
        raise SandboxError(f"Sandbox execution raised: {type(exc).__name__}: {exc}") from exc

    # Caller may have rebound `canvas` to a fresh instance — honor it.
    final = locals_dict.get("canvas") or globals_dict.get("canvas")
    if not isinstance(final, Canvas):
        raise SandboxError(f"Sandbox code must produce a Canvas; got {type(final).__name__}")
    return final


async def execute_python_diagram(
    code: str,
    timeout: float = EXEC_TIMEOUT_SECONDS,  # noqa: ASYNC109 — explicit deadline as public API
) -> Canvas:
    """Run LLM-authored sandbox code; return the produced Canvas.

    The script runs in a thread (via ``asyncio.to_thread``) so the worker
    event loop stays responsive. On timeout we raise — the thread may
    keep running until it exits naturally, accepted limitation per the
    module docstring.
    """
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_run_sync, code),
            timeout=timeout,
        )
    except TimeoutError as exc:
        raise SandboxError(f"Sandbox execution exceeded {timeout}s timeout") from exc
