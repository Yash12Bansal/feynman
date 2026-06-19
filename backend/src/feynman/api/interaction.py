"""Interaction-layer endpoints — question checkpoints + attempt submission.

`GET /interaction/checkpoint`  → the question to show after a topic (no answer).
`POST /interaction/attempts`   → server-side correctness check, records the
                                  attempt to the student graph, reveals the
                                  solution. The correct answer never reaches the
                                  client before this call (anti-cheat).
"""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from feynman.config import settings
from feynman.interaction.models import (
    KIND_FOR_TYPE,
    AttemptOutcome,
    CheckpointQuestion,
    Solution,
)
from feynman.interaction.questions import load_question, load_topic_questions
from feynman.interaction.solution import (
    build_question_visual,
    checkpoint_from_question,
    get_or_build_solution,
)
from feynman.knowledge import StudentGraphStore

router = APIRouter()


def _allowed_types(mode: str) -> set[str]:
    return {"mcq"} if mode == "mcq" else {"mcq", "solved_example"}


@router.get("/checkpoint", response_model=CheckpointQuestion | None)
async def get_checkpoint(topic_id: str, mode: str | None = None) -> CheckpointQuestion | None:
    """The first question for a topic matching the configured mode, or null
    when the topic has none (→ no checkpoint, lecture flows on)."""
    mode = mode or settings.interaction_question_mode
    allowed = _allowed_types(mode)
    for q in await load_topic_questions(topic_id):
        if q.type in allowed:
            # Ensure the question's setup diagram is built + cached (idempotent).
            # The frontend calls this on topic-START, so the whole topic is the
            # generation window — the figure is ready by the time it's shown.
            await build_question_visual(q)
            return checkpoint_from_question(q, KIND_FOR_TYPE[q.type])
    return None


@router.get("/solution", response_model=Solution)
async def get_solution(question_id: str) -> Solution:
    """The worked solution for a question (text + audio + optional board
    diagram). Cached on first build, reused forever. The frontend calls this
    during the student's solving time so the diagram is ready by submit."""
    solution = await get_or_build_solution(question_id)
    if solution is None:
        raise HTTPException(status_code=404, detail="question not found")
    return solution


class AttemptRequest(BaseModel):
    session_id: str  # the study session opened on lecture-open (links to student)
    question_id: str
    selected_option: str | None = None  # MCQ: "A" / "B" / ...
    answer_text: str | None = None  # subjective (Phase C)


@router.post("/attempts", response_model=AttemptOutcome)
async def submit_attempt(body: AttemptRequest) -> AttemptOutcome:
    question = await load_question(body.question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="question not found")

    if question.type == "mcq":
        correct = _mcq_correct(body.selected_option, question.answer)
        mode = "mcq"
    else:
        # Phase C wires the subjective judge here; until then it never blocks —
        # the student still gets the full solution below.
        correct = False
        mode = "subjective"

    # The worked steps are generated + cached during the solving window; read
    # them back (cache hit → instant) so the memory card can show the reasoning,
    # not just the letter. Best-effort — a miss just omits the steps.
    solution = await get_or_build_solution(question.question_id)
    solution_steps = solution.steps if solution else []

    store = StudentGraphStore.connect()
    try:
        await store.record_attempt(
            session_id=body.session_id,
            question_id=question.question_id,
            topic_id=question.topic_id,
            q_text=question.q_text,
            options=question.options,
            solution=question.answer,
            solution_steps=solution_steps,
            correct=correct,
            mode=mode,
            created_at=int(time.time() * 1000),
        )
    finally:
        await store.close()

    return AttemptOutcome(
        correct=correct,
        answer=question.answer,
        answer_audio_url=question.answer_audio_url,
    )


def _mcq_correct(selected: str | None, answer: str) -> bool:
    """Compare the option LETTER, tolerant of 'A' vs 'A. ...' on either side."""
    if not selected or not answer:
        return False
    return selected.strip().upper()[:1] == answer.strip().upper()[:1]
