"""LessonPlan — the inspectable, persisted artifact a teacher would recognise.

Doc 19 §11. This module defines the Pydantic shapes ONLY. No planner, no LLM
call. Phase C wires `plan_lesson` against this surface; the §7 hand-build proof
constructs a LessonPlan as a literal Pydantic object to validate end-to-end
before Phase C exists.

The validators encode the bar. Each is a single rule with a paper-trail back to
doc 19:
  - Hook.forbid_generic_openers: §5 (lecture MUST open with a real hook —
    not "in this section / lecture / we will study / learn …").
  - DiagramRequirement.element_ids_unique: §3 (every element a narration step
    refers to must have a stable id; ids must be unique within a diagram).
  - ChoreographyStep.question_xor_payoff: §5 (a step is either a question or a
    payoff, not both — confusing the two destroys the rhythm).
  - LessonPlan.has_question_payoff_pair: §5 (every topic must contain at least
    one Q→P pair).
  - LessonPlan.crucial_facts_pressed_twice: §5 (each crucial_fact must be
    pressed twice across the choreography — the "press twice" mechanism).
  - LessonPlan.choreography_references_declared_elements: §3 (you cannot point
    at something you didn't put on the board — diagrams generated AFTER the
    plan, FROM the plan; this validator catches a planner that drifts).
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# ──────────────────────────────────────────────────────────────────────────────
# Hook
# ──────────────────────────────────────────────────────────────────────────────


class HookType(str, Enum):
    """How the lecture opens. Anything that makes a Year-9 student lean in."""

    question = "question"
    fact = "fact"
    paradox = "paradox"
    observation = "observation"


# Openers we ban: classic textbook / classroom-recitation phrasings.
# Lower-cased, stripped of leading whitespace before comparing.
_FORBIDDEN_HOOK_OPENERS: tuple[str, ...] = (
    "in this section",
    "in this lecture",
    "in this chapter",
    "in this topic",
    "we will study",
    "we will learn",
    "today we will",
    "let us study",
    "let us learn",
    "let's study",
    "let's learn",
)


class Hook(BaseModel):
    """Doc 19 §5. The lecture's first 8–15 seconds. No TOC, no definition."""

    type: HookType
    text: str

    @field_validator("text")
    @classmethod
    def forbid_generic_openers(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Hook text cannot be empty")
        lower = stripped.lower()
        for opener in _FORBIDDEN_HOOK_OPENERS:
            if lower.startswith(opener):
                raise ValueError(
                    f"Hook text cannot open with {opener!r} — opener must be a "
                    f"real question, fact, paradox, or observation that makes "
                    f"a 13-year-old curious. Doc 19 §5."
                )
        return stripped


# ──────────────────────────────────────────────────────────────────────────────
# Diagram requirement
# ──────────────────────────────────────────────────────────────────────────────


class ElementRequirement(BaseModel):
    """A single element the planner declares the diagram must contain.

    `element_id` is the stable id the choreography references. `role` is the
    human-readable semantic tag (vector, curve, etc.). `description` tells the
    DiagramSpec generator what to actually draw.
    """

    element_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    description: str = Field(min_length=1)


class DiagramRequirement(BaseModel):
    """A diagram the lesson commits to using. Phase D's DiagramSpec generator
    is responsible for emitting a spec whose dictionary contains every
    `element_id` in `required_elements` — that's the diagram-coupling contract.
    """

    diagram_id: str = Field(min_length=1)
    purpose: str = Field(min_length=1, description="The insight this diagram supports.")
    required_elements: list[ElementRequirement] = Field(min_length=1)
    presentation_mode: Literal["build_up", "overview"] = "build_up"

    @field_validator("required_elements")
    @classmethod
    def element_ids_unique(
        cls, value: list[ElementRequirement]
    ) -> list[ElementRequirement]:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for element in value:
            if element.element_id in seen:
                duplicates.add(element.element_id)
            seen.add(element.element_id)
        if duplicates:
            raise ValueError(
                f"required_elements have duplicate element_id(s): {sorted(duplicates)!r}"
            )
        return value


# ──────────────────────────────────────────────────────────────────────────────
# Choreography
# ──────────────────────────────────────────────────────────────────────────────


class ChoreographyAction(str, Enum):
    """The live-annotation primitives the planner can call on, doc 19 §12."""

    focus = "focus"
    unfocus = "unfocus"
    trace = "trace"
    mark_point = "mark_point"
    point_at = "point_at"
    write_margin = "write_margin"
    clear = "clear"


class ChoreographyStep(BaseModel):
    """A single step of the lesson — what gets said + what happens on the
    board, in sync. The narration is the agent's exact words at this step.
    """

    narration: str = Field(min_length=1)
    actions: list[ChoreographyAction] = Field(default_factory=list)
    target_element_id: str | None = None
    target_diagram_id: str | None = Field(
        default=None,
        description="If actions reference a specific diagram, the diagram_id.",
    )
    is_question: bool = False
    is_payoff: bool = False
    presses_crucial_fact: bool = False
    # Book-coverage USP. Set ONLY by BookExampleWeaver for steps it generates
    # to solve a book example faithfully. The pair (is_book_example=True,
    # book_example_ref=i) means this step is part of solving
    # Topic.book_examples[i]. Used by the hard structural validator to
    # guarantee every book example becomes one or more choreography steps.
    is_book_example: bool = False
    book_example_ref: int | None = None
    # Great-teacher colour. Set ONLY by ExtendedExampleWeaver for steps it
    # generates from Topic.extended_examples[i] (real-world anchors + fun
    # facts). Mirrors the book-example tagging so the weaver can strip its
    # own steps on a re-run without disturbing concept or book-example steps.
    is_extended_example: bool = False
    extended_example_ref: int | None = None

    @model_validator(mode="after")
    def question_xor_payoff(self) -> ChoreographyStep:
        if self.is_question and self.is_payoff:
            raise ValueError(
                "ChoreographyStep cannot be both is_question and is_payoff — a "
                "step is either the question or the payoff, never both. Doc 19 §5."
            )
        return self


# ──────────────────────────────────────────────────────────────────────────────
# Equations
# ──────────────────────────────────────────────────────────────────────────────


class EquationIntroduction(BaseModel):
    """An equation, plus the step after which the picture has made it obvious.

    Doc 19 §3: equations arrive AFTER the picture explains them, not before.
    `explanation_in_words` is the plain-language sentence the agent must say
    BEFORE the symbols appear on the board.
    """

    latex: str = Field(min_length=1)
    introduces_after_step_index: int = Field(
        ge=0,
        description="Index into LessonPlan.choreography. The equation appears "
        "AFTER this step has been delivered.",
    )
    explanation_in_words: str = Field(
        min_length=1,
        description="Plain-language sentence stated before the symbols. Forces "
        "the planner to verbalize before symbolizing.",
    )


# ──────────────────────────────────────────────────────────────────────────────
# LessonPlan — the artifact
# ──────────────────────────────────────────────────────────────────────────────


class LessonPlan(BaseModel):
    """The persisted, inspectable artifact for one topic.

    Lives in `extraction.json` after Phase C wires the planner. Hand-authored
    in the §7 proof. Validators here are the contract the planner must satisfy.
    """

    topic_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    hook: Hook
    crucial_facts: list[str] = Field(
        min_length=1,
        max_length=2,
        description="The 1–2 facts every student must walk away with. Each is "
        "pressed twice across the choreography.",
    )
    diagrams: list[DiagramRequirement] = Field(
        max_length=2,
        description="0–2 diagrams. Quantity is a cost. Generate the minimum "
        "needed; never more than 2 without justification (doc 19 §4).",
    )
    choreography: list[ChoreographyStep] = Field(min_length=1)
    equations: list[EquationIntroduction] = Field(default_factory=list)

    @model_validator(mode="after")
    def has_question_payoff_pair(self) -> LessonPlan:
        has_question = any(step.is_question for step in self.choreography)
        has_payoff = any(step.is_payoff for step in self.choreography)
        if not (has_question and has_payoff):
            raise ValueError(
                "LessonPlan choreography must contain at least one is_question "
                "step AND at least one is_payoff step. A topic without a Q→P "
                "pair has no rhythm. Doc 19 §5."
            )
        return self

    @model_validator(mode="after")
    def crucial_facts_pressed_twice(self) -> LessonPlan:
        press_count = sum(1 for step in self.choreography if step.presses_crucial_fact)
        expected = 2 * len(self.crucial_facts)
        if press_count < expected:
            raise ValueError(
                f"Each crucial_fact must be pressed twice across the "
                f"choreography. Got {press_count} step(s) with "
                f"presses_crucial_fact=True; expected at least {expected} "
                f"({len(self.crucial_facts)} crucial_fact(s) × 2). Doc 19 §5."
            )
        return self

    @model_validator(mode="after")
    def choreography_references_declared_elements(self) -> LessonPlan:
        declared_ids: set[str] = {
            element.element_id
            for diagram in self.diagrams
            for element in diagram.required_elements
        }
        referenced_ids: set[str] = {
            step.target_element_id
            for step in self.choreography
            if step.target_element_id
        }
        missing = referenced_ids - declared_ids
        if missing:
            raise ValueError(
                f"choreography references element_id(s) not declared in any "
                f"DiagramRequirement: {sorted(missing)!r}. You can only point "
                f"at things you put on the board. Doc 19 §3."
            )
        return self

    @model_validator(mode="after")
    def equation_step_indices_in_range(self) -> LessonPlan:
        max_index = len(self.choreography) - 1
        for i, equation in enumerate(self.equations):
            if equation.introduces_after_step_index > max_index:
                raise ValueError(
                    f"equations[{i}].introduces_after_step_index="
                    f"{equation.introduces_after_step_index} is out of range "
                    f"(choreography has {len(self.choreography)} step(s))."
                )
        return self
