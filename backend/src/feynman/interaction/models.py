"""Models for the in-lecture interaction (question checkpoint) layer.

Anti-cheat by construction: `Question` (with the `answer`) is server-side only.
The client receives `CheckpointQuestion` — no answer — and only learns the
solution via `AttemptOutcome` AFTER it submits.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# The curriculum graph stores `type` as "mcq" | "solved_example"; the client
# speaks "mcq" | "subjective".
QuestionType = Literal["mcq", "solved_example"]
QuestionKind = Literal["mcq", "subjective"]

KIND_FOR_TYPE: dict[str, QuestionKind] = {
    "mcq": "mcq",
    "solved_example": "subjective",
}


class Question(BaseModel):
    """Full question as stored in the curriculum graph. SERVER-SIDE ONLY — the
    `answer` must never be serialised to the client before submit."""

    question_id: str
    topic_id: str = ""
    type: QuestionType
    q_text: str
    options: list[str] = Field(default_factory=list)
    answer: str = ""
    answer_audio_url: str | None = None
    needs_review: bool = False
    # Two independent diagram caches, both lazily filled + reused for every
    # future student. `*_built` distinguishes "not generated yet" from
    # "generated, none needed".
    #   QUESTION diagram — the setup figure shown WITH the question (generated
    #   during the topic, before it ends).
    question_diagram_built: bool = False
    question_diagram_needed: bool = False
    question_diagram_spec: dict | None = None
    #   SOLUTION diagram — the answer figure shown AFTER submit (generated
    #   during the student's solving window).
    solution_diagram_built: bool = False
    solution_diagram_needed: bool = False
    solution_diagram_spec: dict | None = None
    # A plain-language explanation of WHY the answer is correct — generated in
    # the same cached solution call, so the reveal actually teaches instead of
    # just flashing the right letter.
    solution_explanation: str = ""


class Solution(BaseModel):
    """The worked solution served to the client after submit: the explanation,
    audio, plus a board diagram when the concept needs one. `answer` is the raw
    stored answer (an MCQ letter); the client resolves it to the full option."""

    diagram_needed: bool = False
    diagram_spec: dict | None = None
    answer: str = ""
    explanation: str = ""  # why the correct answer is correct (student-facing)
    answer_audio_url: str | None = None


class CheckpointQuestion(BaseModel):
    """What the client gets to render the checkpoint — no answer leaks. May
    carry the question's own setup diagram (NOT the solution's)."""

    question_id: str
    topic_id: str
    kind: QuestionKind
    q_text: str
    options: list[str] = Field(default_factory=list)
    diagram_needed: bool = False
    diagram_spec: dict | None = None


class AttemptOutcome(BaseModel):
    """Returned after the student submits: correctness + the now-revealed
    solution (text + pre-rendered audio). The diagram, when present, is layered
    on in Phase 3."""

    correct: bool
    answer: str
    answer_audio_url: str | None = None
