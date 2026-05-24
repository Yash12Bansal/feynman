"""LessonPlan validators — doc 19 §11.

These tests pin the contract Phase C's planner must satisfy. Every failure
mode here corresponds to a doc-19 anti-pattern; the validators are the bar.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lecture_pipeline_v2.curriculum.lecture_plan.lesson_plan_models import (
    ChoreographyAction,
    ChoreographyStep,
    DiagramRequirement,
    ElementRequirement,
    EquationIntroduction,
    Hook,
    HookType,
    LessonPlan,
)


# ──────────────────────────────────────────────────────────────────────────────
# Hook
# ──────────────────────────────────────────────────────────────────────────────


_FORBIDDEN_OPENERS_TO_TEST = [
    "In this section we'll cover relativity.",
    "in this lecture, we will derive the Lorentz factor.",
    "In this chapter we look at moving frames.",
    "In this topic, you will learn special relativity.",
    "We will study how light behaves in moving frames.",
    "we will learn the principle of relativity.",
    "Today we will derive the time-dilation formula.",
    "Let us study the special theory.",
    "Let us learn what an inertial frame is.",
    "Let's study what happens when a frame moves.",
    "Let's learn the Lorentz transformation today.",
    # Whitespace + case variants:
    "   In This Section we begin...",
    "WE WILL STUDY motion today.",
]


@pytest.mark.parametrize("bad_text", _FORBIDDEN_OPENERS_TO_TEST)
def test_hook_rejects_forbidden_openers(bad_text: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        Hook(type=HookType.fact, text=bad_text)
    assert "Hook text cannot open with" in str(exc_info.value)


@pytest.mark.parametrize(
    "good_text,hook_type",
    [
        (
            "Throw a ball straight up on a moving train and it lands right "
            "back in your hand — as if the train weren't moving at all.",
            HookType.paradox,
        ),
        (
            "What's the fastest thing in the universe?",
            HookType.question,
        ),
        (
            "Light travels at the same speed for everyone — even if you're chasing it.",
            HookType.fact,
        ),
        (
            "A clock on a fast-moving spaceship ticks slower than yours, and "
            "the spaceship's pilot would say the same about your clock.",
            HookType.observation,
        ),
    ],
)
def test_hook_accepts_real_openers(good_text: str, hook_type: HookType) -> None:
    hook = Hook(type=hook_type, text=good_text)
    assert hook.text == good_text.strip()
    assert hook.type == hook_type


def test_hook_rejects_empty_text() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Hook(type=HookType.question, text="   ")
    assert "Hook text cannot be empty" in str(exc_info.value)


# ──────────────────────────────────────────────────────────────────────────────
# DiagramRequirement
# ──────────────────────────────────────────────────────────────────────────────


def _element(eid: str, role: str = "object") -> ElementRequirement:
    return ElementRequirement(
        element_id=eid, role=role, description=f"description for {eid}"
    )


def test_diagram_requirement_rejects_duplicate_element_ids() -> None:
    with pytest.raises(ValidationError) as exc_info:
        DiagramRequirement(
            diagram_id="d1",
            purpose="something",
            required_elements=[
                _element("dup"),
                _element("unique-a"),
                _element("dup"),
            ],
        )
    assert "duplicate element_id" in str(exc_info.value)


def test_diagram_requirement_accepts_unique_element_ids() -> None:
    diagram = DiagramRequirement(
        diagram_id="d1",
        purpose="something",
        required_elements=[_element("a"), _element("b"), _element("c")],
        presentation_mode="overview",
    )
    assert len(diagram.required_elements) == 3
    assert diagram.presentation_mode == "overview"


def test_diagram_requirement_defaults_to_build_up() -> None:
    diagram = DiagramRequirement(
        diagram_id="d1",
        purpose="something",
        required_elements=[_element("a")],
    )
    assert diagram.presentation_mode == "build_up"


def test_diagram_requirement_rejects_empty_required_elements() -> None:
    with pytest.raises(ValidationError):
        DiagramRequirement(
            diagram_id="d1",
            purpose="something",
            required_elements=[],
        )


# ──────────────────────────────────────────────────────────────────────────────
# ChoreographyStep
# ──────────────────────────────────────────────────────────────────────────────


def test_choreography_step_rejects_question_and_payoff_both_true() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ChoreographyStep(
            narration="What about that?",
            is_question=True,
            is_payoff=True,
        )
    assert "cannot be both is_question and is_payoff" in str(exc_info.value)


def test_choreography_step_accepts_neither_flag() -> None:
    step = ChoreographyStep(narration="just talking")
    assert step.is_question is False
    assert step.is_payoff is False


def test_choreography_step_accepts_actions_list() -> None:
    step = ChoreographyStep(
        narration="trace the curve",
        actions=[ChoreographyAction.focus, ChoreographyAction.trace],
        target_element_id="parabola",
    )
    assert step.actions == [ChoreographyAction.focus, ChoreographyAction.trace]


# ──────────────────────────────────────────────────────────────────────────────
# LessonPlan — top-level cross-field validators
# ──────────────────────────────────────────────────────────────────────────────


def _minimal_diagram() -> DiagramRequirement:
    return DiagramRequirement(
        diagram_id="d1",
        purpose="show the thing",
        required_elements=[_element("el-a"), _element("el-b")],
    )


def _ok_hook() -> Hook:
    return Hook(
        type=HookType.paradox,
        text="A ball thrown up on a moving train lands right back in your hand.",
    )


def _make_lesson_plan(**overrides) -> LessonPlan:
    """Construct a minimal valid LessonPlan; tests override fields to exercise validators."""
    defaults: dict = dict(
        topic_id="t1",
        title="Test topic",
        hook=_ok_hook(),
        crucial_facts=["horizontal velocity is conserved"],
        diagrams=[_minimal_diagram()],
        choreography=[
            ChoreographyStep(
                narration="Setup the scene.",
                actions=[ChoreographyAction.focus],
                target_element_id="el-a",
            ),
            ChoreographyStep(
                narration="If the ball isn't pushed forward, how does it land back in the hand?",
                is_question=True,
            ),
            ChoreographyStep(
                narration="Because horizontal velocity is conserved — nothing took it away.",
                is_payoff=True,
                presses_crucial_fact=True,
            ),
            ChoreographyStep(
                narration="Horizontal velocity stays with the ball through the throw.",
                presses_crucial_fact=True,
            ),
        ],
        equations=[],
    )
    defaults.update(overrides)
    return LessonPlan(**defaults)


def test_lesson_plan_valid_minimal_smoke() -> None:
    plan = _make_lesson_plan()
    assert plan.hook.text.startswith("A ball")
    assert len(plan.choreography) == 4


def test_lesson_plan_rejects_no_question_step() -> None:
    with pytest.raises(ValidationError) as exc_info:
        _make_lesson_plan(
            choreography=[
                ChoreographyStep(
                    narration="Just delivering content.",
                    is_payoff=True,
                    presses_crucial_fact=True,
                ),
                ChoreographyStep(
                    narration="More content.",
                    presses_crucial_fact=True,
                ),
            ]
        )
    assert "at least one is_question" in str(exc_info.value)


def test_lesson_plan_rejects_no_payoff_step() -> None:
    with pytest.raises(ValidationError) as exc_info:
        _make_lesson_plan(
            choreography=[
                ChoreographyStep(narration="Question?", is_question=True),
                ChoreographyStep(narration="More talking.", presses_crucial_fact=True),
                ChoreographyStep(narration="Even more.", presses_crucial_fact=True),
            ]
        )
    assert "at least one is_question" in str(exc_info.value) or "is_payoff" in str(
        exc_info.value
    )


def test_lesson_plan_rejects_crucial_fact_pressed_only_once() -> None:
    with pytest.raises(ValidationError) as exc_info:
        _make_lesson_plan(
            crucial_facts=["the conserved velocity"],
            choreography=[
                ChoreographyStep(narration="hmm?", is_question=True),
                ChoreographyStep(
                    narration="velocity is conserved.",
                    is_payoff=True,
                    presses_crucial_fact=True,
                ),
            ],
        )
    assert "pressed twice" in str(exc_info.value)


def test_lesson_plan_accepts_two_crucial_facts_pressed_twice_each() -> None:
    plan = _make_lesson_plan(
        crucial_facts=["fact one", "fact two"],
        choreography=[
            ChoreographyStep(narration="press one.", presses_crucial_fact=True),
            ChoreographyStep(narration="press one again.", presses_crucial_fact=True),
            ChoreographyStep(narration="why?", is_question=True),
            ChoreographyStep(
                narration="press two as payoff.",
                is_payoff=True,
                presses_crucial_fact=True,
            ),
            ChoreographyStep(narration="press two again.", presses_crucial_fact=True),
        ],
    )
    assert len(plan.crucial_facts) == 2


def test_lesson_plan_rejects_choreography_referencing_undeclared_element_id() -> None:
    with pytest.raises(ValidationError) as exc_info:
        _make_lesson_plan(
            choreography=[
                ChoreographyStep(
                    narration="point at the mystery thing",
                    target_element_id="not-in-diagram",
                ),
                ChoreographyStep(narration="why?", is_question=True),
                ChoreographyStep(
                    narration="because reasons.",
                    is_payoff=True,
                    presses_crucial_fact=True,
                ),
                ChoreographyStep(narration="again.", presses_crucial_fact=True),
            ]
        )
    assert "not declared" in str(exc_info.value)
    assert "not-in-diagram" in str(exc_info.value)


def test_lesson_plan_rejects_zero_crucial_facts() -> None:
    with pytest.raises(ValidationError):
        _make_lesson_plan(crucial_facts=[])


def test_lesson_plan_rejects_three_crucial_facts() -> None:
    with pytest.raises(ValidationError):
        _make_lesson_plan(crucial_facts=["a", "b", "c"])


def test_lesson_plan_rejects_three_diagrams() -> None:
    with pytest.raises(ValidationError):
        _make_lesson_plan(
            diagrams=[
                DiagramRequirement(
                    diagram_id=f"d{i}",
                    purpose="purpose",
                    required_elements=[_element(f"el-{i}-a")],
                )
                for i in range(3)
            ]
        )


def test_lesson_plan_allows_zero_diagrams() -> None:
    plan = _make_lesson_plan(
        diagrams=[],
        choreography=[
            ChoreographyStep(narration="words only."),
            ChoreographyStep(narration="why?", is_question=True),
            ChoreographyStep(
                narration="because.", is_payoff=True, presses_crucial_fact=True
            ),
            ChoreographyStep(narration="again.", presses_crucial_fact=True),
        ],
    )
    assert plan.diagrams == []


def test_lesson_plan_rejects_equation_index_out_of_range() -> None:
    with pytest.raises(ValidationError) as exc_info:
        _make_lesson_plan(
            equations=[
                EquationIntroduction(
                    latex="v = v_0",
                    introduces_after_step_index=99,
                    explanation_in_words="velocity equals initial velocity",
                )
            ]
        )
    assert "out of range" in str(exc_info.value)


def test_lesson_plan_accepts_equation_in_range() -> None:
    plan = _make_lesson_plan(
        equations=[
            EquationIntroduction(
                latex="v_x = v_{0x}",
                introduces_after_step_index=2,
                explanation_in_words="horizontal velocity stays the same",
            )
        ]
    )
    assert plan.equations[0].latex == "v_x = v_{0x}"


# ──────────────────────────────────────────────────────────────────────────────
# §7 worked example — ball thrown straight up in a moving train
# ──────────────────────────────────────────────────────────────────────────────


def test_lesson_plan_section_7_worked_example_validates() -> None:
    """Doc 19 §7. Smoke test that the validators all pass together for the
    canonical ball-in-moving-train lesson. If this breaks, the §7 hand-build
    proof is broken too — that's the gate Phase C+ depends on.
    """

    plan = LessonPlan(
        topic_id="phys-rel-relativity-of-motion",
        title="Ball thrown straight up in a moving train",
        hook=Hook(
            type=HookType.paradox,
            text=(
                "Throw a ball straight up on a moving train and it lands right "
                "back in your hand — as if the train weren't moving at all. "
                "But someone watching from the platform swears the ball flew "
                "in a curve. Both of them are right. How?"
            ),
        ),
        crucial_facts=[
            "horizontal velocity is conserved across the throw",
            "the path of the ball depends on who is watching",
        ],
        diagrams=[
            DiagramRequirement(
                diagram_id="train-frame",
                purpose=(
                    "Show the same throw from two reference frames side-by-side "
                    "so the conserved horizontal velocity becomes visible."
                ),
                required_elements=[
                    ElementRequirement(
                        element_id="train-car",
                        role="boundary",
                        description="rectangle outlining the moving train",
                    ),
                    ElementRequirement(
                        element_id="passenger",
                        role="figure",
                        description="stick figure inside the train",
                    ),
                    ElementRequirement(
                        element_id="vertical-drop-train-frame",
                        role="trajectory",
                        description="straight up-and-down path in the train frame",
                    ),
                    ElementRequirement(
                        element_id="parabola-ground-frame",
                        role="curve",
                        description="parabolic path as seen from the platform",
                    ),
                    ElementRequirement(
                        element_id="train-velocity-vector",
                        role="vector",
                        description="horizontal arrow showing v_train",
                    ),
                    ElementRequirement(
                        element_id="landing-point",
                        role="point",
                        description="the spot on the moving hand where the ball returns",
                    ),
                ],
                presentation_mode="build_up",
            )
        ],
        choreography=[
            ChoreographyStep(
                narration=(
                    "Throw a ball straight up on a moving train and it lands "
                    "right back in your hand. From inside, it's a vertical drop."
                ),
                actions=[ChoreographyAction.focus, ChoreographyAction.trace],
                target_element_id="vertical-drop-train-frame",
                target_diagram_id="train-frame",
            ),
            ChoreographyStep(
                narration=(
                    "Now step outside, onto the platform. The same throw — but "
                    "the train is moving forward this whole time."
                ),
                actions=[ChoreographyAction.focus],
                target_element_id="train-velocity-vector",
                target_diagram_id="train-frame",
            ),
            ChoreographyStep(
                narration=(
                    "From the platform, the ball doesn't go straight up. It "
                    "flies in a curve."
                ),
                actions=[ChoreographyAction.trace],
                target_element_id="parabola-ground-frame",
                target_diagram_id="train-frame",
            ),
            ChoreographyStep(
                narration=(
                    "If the ball isn't being pushed forward once it leaves the "
                    "hand, how does it keep up with the train?"
                ),
                is_question=True,
            ),
            ChoreographyStep(
                narration=(
                    "Because nothing took its forward speed away. The horizontal "
                    "velocity it had from the train stays with it through the "
                    "throw."
                ),
                is_payoff=True,
                presses_crucial_fact=True,
            ),
            ChoreographyStep(
                narration=(
                    "Horizontal velocity is conserved across the throw — that's "
                    "the key idea."
                ),
                presses_crucial_fact=True,
            ),
            ChoreographyStep(
                narration=("And the ball lands exactly where the hand has moved to."),
                actions=[ChoreographyAction.mark_point],
                target_element_id="landing-point",
                target_diagram_id="train-frame",
            ),
            ChoreographyStep(
                narration=(
                    "So the path of the ball depends entirely on who's watching."
                ),
                presses_crucial_fact=True,
            ),
            ChoreographyStep(
                narration=("Same throw, two different shapes — both correct."),
                presses_crucial_fact=True,
            ),
        ],
        equations=[
            EquationIntroduction(
                latex="v_x = v_{train}",
                introduces_after_step_index=5,
                explanation_in_words=(
                    "the ball's horizontal speed always equals the train's speed"
                ),
            ),
        ],
    )
    assert plan.topic_id == "phys-rel-relativity-of-motion"
    assert len(plan.choreography) == 9
    assert len(plan.diagrams) == 1
    assert plan.diagrams[0].diagram_id == "train-frame"
    assert any(step.is_question for step in plan.choreography)
    assert any(step.is_payoff for step in plan.choreography)
