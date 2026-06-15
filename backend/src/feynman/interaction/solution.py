"""Solution builder — lazy, cached, one LLM call.

`get_or_build_solution` returns a question's worked solution (text + audio +
optional board diagram). On a cache MISS it makes ONE chain-of-thought
Anthropic call that returns `{diagram_needed, diagram_spec}`, persists the
result on the Question node, and returns it — so the next student (and every
student after) reuses it with no LLM call. Generation overlaps the current
student's solving time, so the latency is hidden.

Failures never block: any error → a text-only solution (diagram_needed=false),
NOT cached, so it retries next time.
"""

from __future__ import annotations

from typing import Any

import anthropic
import structlog

from feynman.config import settings
from feynman.interaction.models import CheckpointQuestion, Question, Solution
from feynman.interaction.questions import (
    cache_question_diagram,
    cache_solution_diagram,
    load_question,
)
from feynman.interaction.solution_prompt import (
    SOLUTION_DIAGRAM_SYSTEM,
    build_question_user_prompt,
    build_solution_user_prompt,
)

logger = structlog.get_logger()

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 4096
_TOOL_NAME = "emit_solution_diagram"
_TOOL_DESCRIPTION = (
    "Emit whether the solution needs a diagram and, if so, the DesignDiagramSpec."
)
_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "steps": {"type": "array", "items": {"type": "string"}},
        "diagram_needed": {"type": "boolean"},
        "diagram_spec": {"type": ["object", "null"]},
    },
    "required": ["diagram_needed"],
}


def _solution_from_question(q: Question) -> Solution:
    return Solution(
        diagram_needed=q.solution_diagram_needed,
        diagram_spec=q.solution_diagram_spec,
        answer=q.answer,
        steps=q.solution_steps,
        answer_audio_url=q.answer_audio_url,
    )


async def get_or_build_solution(question_id: str) -> Solution | None:
    """Return the cached solution, or build + cache it on first demand.

    Returns None only when the question doesn't exist.
    """
    q = await load_question(question_id)
    if q is None:
        return None
    # Cache hit only when a prior build ALSO produced the steps. Nodes cached
    # before stepped solutions existed (built=true, no steps) fall through and
    # regenerate once, self-healing the stale cache.
    if q.solution_diagram_built and q.solution_steps:
        return _solution_from_question(q)

    steps, needed, spec = await _call_diagram_llm(
        build_solution_user_prompt(
            q_text=q.q_text, answer=q.answer, options=q.options
        ),
        question_id=question_id,
    )

    if needed is None:
        # Generation errored — serve text-only now, leave UNcached so a later
        # request retries. The student still gets the answer (+ any steps).
        return Solution(
            diagram_needed=False,
            answer=q.answer,
            steps=steps,
            answer_audio_url=q.answer_audio_url,
        )

    try:
        await cache_solution_diagram(
            question_id,
            diagram_needed=needed,
            diagram_spec=spec,
            steps=steps,
        )
    except Exception:
        logger.warning("solution.cache_write_failed", question_id=question_id)

    return Solution(
        diagram_needed=needed,
        diagram_spec=spec if needed else None,
        answer=q.answer,
        steps=steps,
        answer_audio_url=q.answer_audio_url,
    )


async def build_question_visual(q: Question) -> None:
    """Ensure the QUESTION's setup diagram is built + cached (idempotent).

    Called when the student lands on the topic — the whole topic is the
    generation window, so the figure is ready when the topic ends. Mutates the
    passed Question in place so the caller can return it without re-loading.
    """
    if q.question_diagram_built:
        return
    _steps, needed, spec = await _call_diagram_llm(
        build_question_user_prompt(q_text=q.q_text), question_id=q.question_id
    )
    if needed is None:
        return  # error — leave uncached, retry next time; question shows text-only
    try:
        await cache_question_diagram(
            q.question_id, diagram_needed=needed, diagram_spec=spec
        )
    except Exception:
        logger.warning("question_visual.cache_write_failed", question_id=q.question_id)
    q.question_diagram_built = True
    q.question_diagram_needed = needed
    q.question_diagram_spec = spec if needed else None


def checkpoint_from_question(q: Question, kind: str) -> CheckpointQuestion:
    """Build the client-facing checkpoint (no answer) including the question's
    own setup diagram."""
    return CheckpointQuestion(
        question_id=q.question_id,
        topic_id=q.topic_id,
        kind=kind,  # type: ignore[arg-type]
        q_text=q.q_text,
        options=q.options,
        diagram_needed=q.question_diagram_needed,
        diagram_spec=q.question_diagram_spec,
    )


async def _call_diagram_llm(
    user_prompt: str, *, question_id: str
) -> tuple[list[str], bool | None, dict[str, Any] | None]:
    """One Anthropic CoT call → (steps, diagram_needed, diagram_spec).
    `steps` is [] for question-setup calls (which don't request it).
    Returns ([], None, None) on any failure so the caller can fall back without
    caching."""
    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key or "")
        response = await client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=SOLUTION_DIAGRAM_SYSTEM,
            messages=[{"role": "user", "content": user_prompt}],
            tools=[
                {
                    "name": _TOOL_NAME,
                    "description": _TOOL_DESCRIPTION,
                    "input_schema": _INPUT_SCHEMA,
                }
            ],
            tool_choice={"type": "tool", "name": _TOOL_NAME},
        )
    except Exception as exc:
        logger.warning("diagram_llm.failed", question_id=question_id, error=str(exc)[:200])
        return [], None, None

    for block in response.content:
        if (
            getattr(block, "type", None) == "tool_use"
            and getattr(block, "name", None) == _TOOL_NAME
        ):
            payload = block.input
            if not isinstance(payload, dict):
                return [], None, None
            raw_steps = payload.get("steps")
            steps = (
                [str(s).strip() for s in raw_steps if str(s).strip()]
                if isinstance(raw_steps, list)
                else []
            )
            needed = bool(payload.get("diagram_needed"))
            spec = payload.get("diagram_spec") if needed else None
            spec = spec if isinstance(spec, dict) else None
            # "Needed but no usable spec" → treat as not-needed rather than
            # caching a broken diagram.
            if needed and spec is None:
                needed = False
            return steps, needed, spec

    return [], None, None
