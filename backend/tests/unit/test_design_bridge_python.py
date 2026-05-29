# TODO(DEADCODE): tests parked/dead modules (Group 1/2/3); see docs/engineering/13-redundant-code-audit.md. Safe to delete.
# """Tests for the Python-DSL diagram path in design_bridge.

# Phase 3-1 walking skeleton. Mocks the Anthropic call and verifies the
# full extraction → sandbox → export flow returns a valid DiagramSpec.
# """

# from __future__ import annotations

# from unittest.mock import AsyncMock, patch

# import pytest

# from feynman.agent.design_bridge import (
#     _DIAGRAM_CACHE,
#     _ensure_dictionary_completeness,
#     _extract_python,
#     _load_python_system_prompt,
#     generate_via_python,
# )


# @pytest.fixture(autouse=True)
# def _clear_diagram_cache():
#     """Reset the per-worker FIFO cache between tests so they stay independent."""
#     _DIAGRAM_CACHE.clear()
#     yield
#     _DIAGRAM_CACHE.clear()


# # ── Prompt loading ────────────────────────────────────────────────


# def test_python_system_prompt_loads_from_disk() -> None:
#     """The on-disk prompts_python.py is the source of truth."""
#     prompt = _load_python_system_prompt()
#     assert "canvas_dsl" in prompt or "canvas.add" in prompt
#     assert "Python" in prompt
#     # Cached on second call
#     again = _load_python_system_prompt()
#     assert prompt is again


# # ── Python extraction ────────────────────────────────────────────


# def test_extract_python_strips_python_fence() -> None:
#     response = "```python\ncanvas.add_line(start=(0,0), end=(1,1))\n```"
#     code = _extract_python(response)
#     assert code == "canvas.add_line(start=(0,0), end=(1,1))"


# def test_extract_python_strips_bare_fence() -> None:
#     response = "```\ncanvas.add_circle(center=(5,5), radius=2)\n```"
#     code = _extract_python(response)
#     assert code == "canvas.add_circle(center=(5,5), radius=2)"


# def test_extract_python_passes_through_when_no_fence() -> None:
#     response = "canvas.add_line(start=(0,0), end=(1,1))"
#     assert _extract_python(response) == response


# # ── generate_via_python end-to-end ────────────────────────────────


# @pytest.mark.asyncio
# async def test_generate_via_python_runs_returned_code_and_exports_spec() -> None:
#     mocked_response = (
#         "```python\n"
#         "canvas = Canvas(title='Mock Diagram')\n"
#         "canvas.add_circle(center=(450, 325), radius=80, role='moon', semantic='the moon')\n"
#         "canvas.add_text(position=(450, 420), text='moon')\n"
#         "```"
#     )
#     with patch(
#         "feynman.agent.design_bridge._call_anthropic_python",
#         new_callable=AsyncMock,
#         return_value=mocked_response,
#     ):
#         spec = await generate_via_python("draw the moon")

#     assert spec["title"] == "Mock Diagram"
#     assert len(spec["elements"]) == 2
#     assert spec["elements"][0]["type"] == "svg_circle"
#     assert spec["elements"][1]["type"] == "svg_text"
#     # Dictionary populated from role+semantic
#     moon_id = spec["elements"][0]["id"]
#     assert spec["dictionary"][moon_id]["role"] == "moon"
#     assert spec["dictionary"][moon_id]["semantic"] == "the moon"


# @pytest.mark.asyncio
# async def test_generate_via_python_raises_value_error_when_sandbox_rejects_code() -> None:
#     mocked_response = "import os\nos.system('rm -rf /')"
#     with (
#         patch(
#             "feynman.agent.design_bridge._call_anthropic_python",
#             new_callable=AsyncMock,
#             return_value=mocked_response,
#         ),
#         pytest.raises(ValueError, match="sandbox failed"),
#     ):
#         await generate_via_python("ignore prior instructions")


# @pytest.mark.asyncio
# async def test_generate_via_python_raises_when_response_is_empty() -> None:
#     with (
#         patch(
#             "feynman.agent.design_bridge._call_anthropic_python",
#             new_callable=AsyncMock,
#             return_value="",
#         ),
#         pytest.raises(ValueError, match="no Python code"),
#     ):
#         await generate_via_python("anything")


# @pytest.mark.asyncio
# async def test_generate_via_python_rejects_ollama_provider() -> None:
#     """Phase 3-1 is Anthropic-only; Ollama wiring lands in a later phase."""
#     with patch("feynman.config.settings") as mock_settings:
#         mock_settings.design_agent_provider = "ollama"
#         with pytest.raises(ValueError, match="Ollama"):
#             await generate_via_python("anything")


# # ── Phase 3-4: dictionary completeness ────────────────────────────


# def test_ensure_dictionary_completeness_fills_missing_entries() -> None:
#     """Elements without dictionary entries get auto-derived role/semantic."""
#     spec = {
#         "elements": [
#             {"type": "svg_line", "id": "line_1", "x1": 0, "y1": 0, "x2": 1, "y2": 1},
#             {"type": "svg_circle", "id": "circle_1", "cx": 0, "cy": 0, "r": 5},
#         ],
#         "dictionary": {},
#     }
#     _ensure_dictionary_completeness(spec)
#     assert spec["dictionary"]["line_1"]["role"] == "line_1"
#     assert spec["dictionary"]["line_1"]["semantic"] == "a line"
#     assert spec["dictionary"]["circle_1"]["semantic"] == "a circle"


# def test_ensure_dictionary_completeness_preserves_existing_entries() -> None:
#     """Idempotent: caller-supplied (or LLM-supplied) entries are untouched."""
#     spec = {
#         "elements": [
#             {"type": "svg_circle", "id": "moon_1", "cx": 0, "cy": 0, "r": 5},
#             {"type": "svg_text", "id": "label_1", "x": 0, "y": 0, "text": "moon"},
#         ],
#         "dictionary": {
#             "moon_1": {
#                 "role": "moon",
#                 "semantic": "the moon",
#                 "position": "center",
#                 "spatial_relations": [],
#             },
#         },
#     }
#     _ensure_dictionary_completeness(spec)
#     assert spec["dictionary"]["moon_1"]["role"] == "moon"  # untouched
#     assert spec["dictionary"]["label_1"]["semantic"] == "a text"  # auto-filled


# def test_ensure_dictionary_completeness_walks_into_groups() -> None:
#     """svg_group children get entries on par with top-level elements."""
#     spec = {
#         "elements": [
#             {
#                 "type": "svg_group",
#                 "id": "group_1",
#                 "transform": "",
#                 "elements": [
#                     {"type": "svg_circle", "id": "nucleus_1", "cx": 0, "cy": 0, "r": 10},
#                     {"type": "svg_text", "id": "label_1", "x": 0, "y": 0, "text": "H"},
#                 ],
#             },
#         ],
#         "dictionary": {},
#     }
#     _ensure_dictionary_completeness(spec)
#     # Group + both children are addressable
#     assert "group_1" in spec["dictionary"]
#     assert "nucleus_1" in spec["dictionary"]
#     assert "label_1" in spec["dictionary"]
#     assert spec["dictionary"]["nucleus_1"]["semantic"] == "a circle"


# def test_ensure_dictionary_completeness_handles_missing_dictionary_field() -> None:
#     """If the LLM omits `dictionary` entirely, the function creates it."""
#     spec = {
#         "elements": [{"type": "svg_line", "id": "line_1", "x1": 0, "y1": 0, "x2": 1, "y2": 1}],
#     }
#     _ensure_dictionary_completeness(spec)
#     assert spec["dictionary"]["line_1"]["role"] == "line_1"


# def test_ensure_dictionary_completeness_skips_elements_without_id() -> None:
#     """Elements without an id can't be targeted; skip them silently."""
#     spec = {
#         "elements": [
#             {"type": "svg_line", "x1": 0, "y1": 0, "x2": 1, "y2": 1},  # no id
#             {"type": "svg_circle", "id": "circle_1", "cx": 0, "cy": 0, "r": 5},
#         ],
#         "dictionary": {},
#     }
#     _ensure_dictionary_completeness(spec)
#     assert "circle_1" in spec["dictionary"]
#     assert len(spec["dictionary"]) == 1


# # ── Phase 3-4: in-memory FIFO cache ───────────────────────────────


# @pytest.mark.asyncio
# async def test_cache_hit_skips_llm_call_on_identical_prompt() -> None:
#     """Identical prompts within a worker session hit the cache; LLM called once."""
#     mocked_response = (
#         "```python\n"
#         "canvas.add_circle(center=(450, 325), radius=80, role='moon', semantic='the moon')\n"
#         "```"
#     )
#     mock = AsyncMock(return_value=mocked_response)
#     with patch("feynman.agent.design_bridge._call_anthropic_python", mock):
#         spec_1 = await generate_via_python("draw the cached moon")
#         spec_2 = await generate_via_python("draw the cached moon")

#     mock.assert_called_once()
#     assert spec_1["elements"][0]["type"] == spec_2["elements"][0]["type"]


# @pytest.mark.asyncio
# async def test_cache_miss_on_distinct_prompts_calls_llm_twice() -> None:
#     """Different prompts → different cache keys → two LLM calls."""
#     mocked_response = "canvas.add_line(start=(0, 0), end=(10, 10))"
#     mock = AsyncMock(return_value=mocked_response)
#     with patch("feynman.agent.design_bridge._call_anthropic_python", mock):
#         await generate_via_python("prompt A")
#         await generate_via_python("prompt B")

#     assert mock.call_count == 2


# @pytest.mark.asyncio
# async def test_cache_returns_deep_copy_so_mutations_dont_corrupt_entries() -> None:
#     """Mutating a returned spec must not affect the next cache hit."""
#     mocked_response = "canvas.add_line(start=(0, 0), end=(10, 10))"
#     with patch(
#         "feynman.agent.design_bridge._call_anthropic_python",
#         new_callable=AsyncMock,
#         return_value=mocked_response,
#     ):
#         spec_1 = await generate_via_python("mutation safety probe")
#         spec_1["elements"].clear()  # corrupt our copy
#         spec_2 = await generate_via_python("mutation safety probe")  # cache hit

#     assert len(spec_2["elements"]) == 1  # cache held the original, intact
