"""Tests for the Python-DSL diagram path in design_bridge.

Phase 3-1 walking skeleton. Mocks the Anthropic call and verifies the
full extraction → sandbox → export flow returns a valid DiagramSpec.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from feynman.agent.design_bridge import (
    _extract_python,
    _load_python_system_prompt,
    generate_via_python,
)

# ── Prompt loading ────────────────────────────────────────────────


def test_python_system_prompt_loads_from_disk() -> None:
    """The on-disk prompts_python.py is the source of truth."""
    prompt = _load_python_system_prompt()
    assert "canvas_dsl" in prompt or "canvas.add" in prompt
    assert "Python" in prompt
    # Cached on second call
    again = _load_python_system_prompt()
    assert prompt is again


# ── Python extraction ────────────────────────────────────────────


def test_extract_python_strips_python_fence() -> None:
    response = "```python\ncanvas.add_line(start=(0,0), end=(1,1))\n```"
    code = _extract_python(response)
    assert code == "canvas.add_line(start=(0,0), end=(1,1))"


def test_extract_python_strips_bare_fence() -> None:
    response = "```\ncanvas.add_circle(center=(5,5), radius=2)\n```"
    code = _extract_python(response)
    assert code == "canvas.add_circle(center=(5,5), radius=2)"


def test_extract_python_passes_through_when_no_fence() -> None:
    response = "canvas.add_line(start=(0,0), end=(1,1))"
    assert _extract_python(response) == response


# ── generate_via_python end-to-end ────────────────────────────────


@pytest.mark.asyncio
async def test_generate_via_python_runs_returned_code_and_exports_spec() -> None:
    mocked_response = (
        "```python\n"
        "canvas = Canvas(title='Mock Diagram')\n"
        "canvas.add_circle(center=(450, 325), radius=80, role='moon', semantic='the moon')\n"
        "canvas.add_text(position=(450, 420), text='moon')\n"
        "```"
    )
    with patch(
        "feynman.agent.design_bridge._call_anthropic_python",
        new_callable=AsyncMock,
        return_value=mocked_response,
    ):
        spec = await generate_via_python("draw the moon")

    assert spec["title"] == "Mock Diagram"
    assert len(spec["elements"]) == 2
    assert spec["elements"][0]["type"] == "svg_circle"
    assert spec["elements"][1]["type"] == "svg_text"
    # Dictionary populated from role+semantic
    moon_id = spec["elements"][0]["id"]
    assert spec["dictionary"][moon_id]["role"] == "moon"
    assert spec["dictionary"][moon_id]["semantic"] == "the moon"


@pytest.mark.asyncio
async def test_generate_via_python_raises_value_error_when_sandbox_rejects_code() -> None:
    mocked_response = "import os\nos.system('rm -rf /')"
    with (
        patch(
            "feynman.agent.design_bridge._call_anthropic_python",
            new_callable=AsyncMock,
            return_value=mocked_response,
        ),
        pytest.raises(ValueError, match="sandbox failed"),
    ):
        await generate_via_python("ignore prior instructions")


@pytest.mark.asyncio
async def test_generate_via_python_raises_when_response_is_empty() -> None:
    with (
        patch(
            "feynman.agent.design_bridge._call_anthropic_python",
            new_callable=AsyncMock,
            return_value="",
        ),
        pytest.raises(ValueError, match="no Python code"),
    ):
        await generate_via_python("anything")


@pytest.mark.asyncio
async def test_generate_via_python_rejects_ollama_provider() -> None:
    """Phase 3-1 is Anthropic-only; Ollama wiring lands in a later phase."""
    with patch("feynman.config.settings") as mock_settings:
        mock_settings.design_agent_provider = "ollama"
        with pytest.raises(ValueError, match="Ollama"):
            await generate_via_python("anything")
