"""Solution builder tests — lazy generation + cache + fallback.

Anthropic + Neo4j loaders/writers are patched. We assert: cache hit skips the
LLM, cache miss generates + persists, errors fall back to text-only WITHOUT
caching, and 'needed but no spec' degrades safely.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from feynman.interaction.models import Question
from feynman.interaction.solution import get_or_build_solution


def _q(
    *,
    built: bool = False,
    needed: bool = False,
    spec: dict | None = None,
    explanation: str = "",
) -> Question:
    return Question(
        question_id="q1",
        topic_id="t1",
        type="mcq",
        q_text="Why does the ball land back in your hand on a moving train?",
        answer="Because horizontal velocity is shared by ball and train.",
        answer_audio_url="/audio/q1.mp3",
        solution_diagram_built=built,
        solution_diagram_needed=needed,
        solution_diagram_spec=spec,
        solution_explanation=explanation,
    )


def _tool_response(payload: dict[str, Any]) -> SimpleNamespace:
    block = SimpleNamespace(type="tool_use", name="emit_solution_diagram", input=payload)
    return SimpleNamespace(content=[block])


def _patch_anthropic(payload: dict[str, Any] | Exception):
    client = AsyncMock()
    client.messages = AsyncMock()
    if isinstance(payload, Exception):
        client.messages.create = AsyncMock(side_effect=payload)
    else:
        client.messages.create = AsyncMock(return_value=_tool_response(payload))
    return patch(
        "feynman.interaction.solution.anthropic.AsyncAnthropic", return_value=client
    )


@pytest.mark.asyncio
async def test_cache_hit_skips_llm():
    spec = {"title": "t", "elements": []}
    # A real cache hit has BOTH the diagram decision AND the explanation — the
    # gate falls through (regenerates) if the explanation is missing.
    cached = _q(built=True, needed=True, spec=spec, explanation="Shared velocity.")
    with (
        patch("feynman.interaction.solution.load_question", AsyncMock(return_value=cached)),
        _patch_anthropic(RuntimeError("must not be called")) as anth,
        patch("feynman.interaction.solution.cache_solution_diagram", AsyncMock()) as writer,
    ):
        sol = await get_or_build_solution("q1")
    assert sol is not None
    assert sol.diagram_needed is True
    assert sol.diagram_spec == spec
    assert sol.answer.startswith("Because")
    anth.return_value.messages.create.assert_not_called()
    writer.assert_not_called()


@pytest.mark.asyncio
async def test_cache_miss_generates_and_persists():
    spec = {"title": "Train frame", "width": 900, "height": 650, "elements": [{"type": "svg_arrow", "id": "v"}]}
    writer = AsyncMock()
    with (
        patch("feynman.interaction.solution.load_question", AsyncMock(return_value=_q())),
        _patch_anthropic({"diagram_needed": True, "diagram_spec": spec}),
        patch("feynman.interaction.solution.cache_solution_diagram", writer),
    ):
        sol = await get_or_build_solution("q1")
    assert sol is not None
    assert sol.diagram_needed is True
    assert sol.diagram_spec == spec
    # Persisted for the next student.
    writer.assert_awaited_once()
    kwargs = writer.await_args.kwargs
    assert kwargs["diagram_needed"] is True
    assert kwargs["diagram_spec"] == spec


@pytest.mark.asyncio
async def test_explanation_is_generated_cached_and_served():
    """The solution call returns a plain-language explanation, which is served
    to the client AND cached on the node for the next student."""
    writer = AsyncMock()
    with (
        patch("feynman.interaction.solution.load_question", AsyncMock(return_value=_q())),
        _patch_anthropic(
            {
                "explanation": "Inertia keeps the ball moving with the train.",
                "diagram_needed": False,
                "diagram_spec": None,
            }
        ),
        patch("feynman.interaction.solution.cache_solution_diagram", writer),
    ):
        sol = await get_or_build_solution("q1")
    assert sol is not None
    assert sol.explanation == "Inertia keeps the ball moving with the train."
    # Persisted alongside the diagram decision.
    assert writer.await_args.kwargs["explanation"] == (
        "Inertia keeps the ball moving with the train."
    )


@pytest.mark.asyncio
async def test_stale_cache_without_explanation_regenerates():
    """A node built BEFORE explanations existed (built=true, explanation empty)
    must NOT be served as-is — it regenerates once to self-heal."""
    writer = AsyncMock()
    stale = _q(built=True, needed=False, spec=None, explanation="")
    with (
        patch("feynman.interaction.solution.load_question", AsyncMock(return_value=stale)),
        _patch_anthropic(
            {"explanation": "Now explained.", "diagram_needed": False, "diagram_spec": None}
        ) as anth,
        patch("feynman.interaction.solution.cache_solution_diagram", writer),
    ):
        sol = await get_or_build_solution("q1")
    anth.return_value.messages.create.assert_called_once()  # regenerated
    assert sol is not None and sol.explanation == "Now explained."
    writer.assert_awaited_once()


@pytest.mark.asyncio
async def test_diagram_not_needed_caches_false_no_spec():
    writer = AsyncMock()
    with (
        patch("feynman.interaction.solution.load_question", AsyncMock(return_value=_q())),
        _patch_anthropic({"diagram_needed": False, "diagram_spec": None}),
        patch("feynman.interaction.solution.cache_solution_diagram", writer),
    ):
        sol = await get_or_build_solution("q1")
    assert sol is not None
    assert sol.diagram_needed is False
    assert sol.diagram_spec is None
    assert sol.answer  # text solution still returned
    writer.assert_awaited_once()
    assert writer.await_args.kwargs["diagram_needed"] is False


@pytest.mark.asyncio
async def test_needed_but_no_spec_degrades_to_false():
    writer = AsyncMock()
    with (
        patch("feynman.interaction.solution.load_question", AsyncMock(return_value=_q())),
        _patch_anthropic({"diagram_needed": True, "diagram_spec": None}),
        patch("feynman.interaction.solution.cache_solution_diagram", writer),
    ):
        sol = await get_or_build_solution("q1")
    assert sol is not None
    assert sol.diagram_needed is False
    assert writer.await_args.kwargs["diagram_needed"] is False


@pytest.mark.asyncio
async def test_generation_error_falls_back_text_only_and_does_not_cache():
    writer = AsyncMock()
    with (
        patch("feynman.interaction.solution.load_question", AsyncMock(return_value=_q())),
        _patch_anthropic(RuntimeError("anthropic down")),
        patch("feynman.interaction.solution.cache_solution_diagram", writer),
    ):
        sol = await get_or_build_solution("q1")
    assert sol is not None
    assert sol.diagram_needed is False
    assert sol.answer.startswith("Because")  # full answer still served
    writer.assert_not_called()  # not cached → retries next time


@pytest.mark.asyncio
async def test_unknown_question_returns_none():
    with patch("feynman.interaction.solution.load_question", AsyncMock(return_value=None)):
        sol = await get_or_build_solution("nope")
    assert sol is None


# ── Question (setup) diagram ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_question_visual_generates_caches_and_mutates():
    from feynman.interaction.solution import build_question_visual

    q = _q()  # question_diagram_built defaults False
    spec = {"title": "circuit", "elements": [{"type": "svg_line", "id": "w"}]}
    writer = AsyncMock()
    with (
        _patch_anthropic({"diagram_needed": True, "diagram_spec": spec}),
        patch("feynman.interaction.solution.cache_question_diagram", writer),
    ):
        await build_question_visual(q)
    # In-place mutation so the endpoint can return without re-loading.
    assert q.question_diagram_built is True
    assert q.question_diagram_needed is True
    assert q.question_diagram_spec == spec
    writer.assert_awaited_once()


@pytest.mark.asyncio
async def test_build_question_visual_skips_when_already_built():
    from feynman.interaction.solution import build_question_visual

    q = _q()
    q.question_diagram_built = True
    writer = AsyncMock()
    with (
        _patch_anthropic(RuntimeError("must not be called")) as anth,
        patch("feynman.interaction.solution.cache_question_diagram", writer),
    ):
        await build_question_visual(q)
    anth.return_value.messages.create.assert_not_called()
    writer.assert_not_called()
