"""Interaction layer tests — checkpoint selection + attempt grading/recording.

Loaders + the student store are patched at the endpoint seam; no Neo4j.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from feynman.api.interaction import (
    AttemptRequest,
    _mcq_correct,
    get_checkpoint,
    submit_attempt,
)
from feynman.interaction.models import Question


def _q(qid: str, qtype: str, answer: str = "A") -> Question:
    return Question(
        question_id=qid,
        topic_id="t1",
        type=qtype,  # type: ignore[arg-type]
        q_text=f"Question {qid}?",
        options=["A. one", "B. two", "C. three", "D. four"],
        answer=answer,
        answer_audio_url=f"/audio/{qid}.mp3",
    )


# ── MCQ correctness helper ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "selected,answer,expected",
    [
        ("A", "A", True),
        ("a", "A", True),  # case-insensitive
        ("B", "A", False),
        ("A", "A. the first option", True),  # tolerant of 'A. ...'
        ("A. one", "A", True),
        (None, "A", False),
        ("A", "", False),
    ],
)
def test_mcq_correct(selected, answer, expected):
    assert _mcq_correct(selected, answer) is expected


# ── Checkpoint selection ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_checkpoint_mcq_mode_skips_subjective():
    """mode=mcq must skip a solved_example and return the first MCQ."""
    questions = [_q("q1", "solved_example"), _q("q2", "mcq")]
    with (
        patch(
            "feynman.api.interaction.load_topic_questions",
            AsyncMock(return_value=questions),
        ),
        patch("feynman.api.interaction.build_question_visual", AsyncMock()),
    ):
        cp = await get_checkpoint(topic_id="t1", mode="mcq")
    assert cp is not None
    assert cp.question_id == "q2"
    assert cp.kind == "mcq"
    # The public shape never carries the answer.
    assert not hasattr(cp, "answer")


@pytest.mark.asyncio
async def test_checkpoint_subjective_mode_allows_solved_example():
    questions = [_q("q1", "solved_example")]
    with (
        patch(
            "feynman.api.interaction.load_topic_questions",
            AsyncMock(return_value=questions),
        ),
        patch("feynman.api.interaction.build_question_visual", AsyncMock()),
    ):
        cp = await get_checkpoint(topic_id="t1", mode="mcq_subjective")
    assert cp is not None
    assert cp.kind == "subjective"


@pytest.mark.asyncio
async def test_checkpoint_returns_null_when_no_match():
    with (
        patch(
            "feynman.api.interaction.load_topic_questions",
            AsyncMock(return_value=[_q("q1", "solved_example")]),
        ),
        patch("feynman.api.interaction.build_question_visual", AsyncMock()),
    ):
        cp = await get_checkpoint(topic_id="t1", mode="mcq")
    assert cp is None


# ── Attempt submission ──────────────────────────────────────────────────────


def _sol(steps: list[str] | None = None):
    return SimpleNamespace(steps=steps or ["Because C is correct."])


@pytest.mark.asyncio
async def test_submit_correct_mcq_records_and_reveals():
    store = AsyncMock()
    with (
        patch(
            "feynman.api.interaction.load_question",
            AsyncMock(return_value=_q("q2", "mcq", answer="C")),
        ),
        patch(
            "feynman.api.interaction.get_or_build_solution",
            AsyncMock(return_value=_sol()),
        ),
        patch(
            "feynman.api.interaction.StudentGraphStore.connect",
            return_value=store,
        ),
    ):
        out = await submit_attempt(
            AttemptRequest(session_id="s1", question_id="q2", selected_option="C")
        )
    assert out.correct is True
    assert out.answer == "C"
    assert out.answer_audio_url == "/audio/q2.mp3"
    # Recorded to the student graph with the right correctness + mode, and the
    # denormalised options + worked steps the memory card needs.
    store.record_attempt.assert_awaited_once()
    kwargs = store.record_attempt.await_args.kwargs
    assert kwargs["correct"] is True
    assert kwargs["mode"] == "mcq"
    assert kwargs["session_id"] == "s1"
    assert kwargs["solution_steps"] == ["Because C is correct."]
    assert kwargs["options"] == _q("q2", "mcq", answer="C").options
    store.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_submit_wrong_mcq_records_incorrect_but_still_reveals():
    store = AsyncMock()
    with (
        patch(
            "feynman.api.interaction.load_question",
            AsyncMock(return_value=_q("q2", "mcq", answer="C")),
        ),
        patch(
            "feynman.api.interaction.get_or_build_solution",
            AsyncMock(return_value=_sol()),
        ),
        patch(
            "feynman.api.interaction.StudentGraphStore.connect",
            return_value=store,
        ),
    ):
        out = await submit_attempt(
            AttemptRequest(session_id="s1", question_id="q2", selected_option="A")
        )
    assert out.correct is False
    # Wrong answer never blocks — the solution is still revealed.
    assert out.answer == "C"
    assert store.record_attempt.await_args.kwargs["correct"] is False


@pytest.mark.asyncio
async def test_submit_unknown_question_404():
    from fastapi import HTTPException

    with patch(
        "feynman.api.interaction.load_question", AsyncMock(return_value=None)
    ), pytest.raises(HTTPException) as exc:
        await submit_attempt(
            AttemptRequest(session_id="s1", question_id="nope", selected_option="A")
        )
    assert exc.value.status_code == 404
