"""Shared planning models.

These models are the single source of truth for both the real-time agent
(`backend/src/feynman/agent/`) and the precompute pipeline
(`data_pre_compute_v2/src/lecture_pipeline_v2/`). The `Field(description=...)`
strings are part of the LLM tool schema — do not edit them without
understanding the contract impact on `plan_concept` / `plan_doubt`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

# ── Data Models ─────────────────────────────────────────────


class VisualBeatAction(BaseModel):
    """A specific visual tool call planned for a teaching beat."""

    tool: str = Field(
        description=(
            "Which visual tool to use. Split-board model:\n"
            "NOTEBOOK panel (right, sequential writing column): write_section, "
            "write_equation, write_step, write_text, write_answer, strikethrough, "
            "new_page, show_equation, step_equation, show_graph, show_text.\n"
            "SLIDE panel (left, one diagram at a time): draw_scene, "
            "draw_design_diagram, modify_design_diagram, draw_diagram.\n"
            "REFERENCE (targets an existing element): highlight_diagram_part, "
            "highlight_walk, annotate, clear_cluster, scroll_board."
        ),
    )
    description: str = Field(
        description="What this visual shows — used as the tool's main content parameter",
    )
    zone: str = Field(
        default="",
        description=(
            "Board zone for SLIDE-panel placement only (notebook writes flow "
            "top-to-bottom automatically). One of: top-left, top-center, "
            "top-right, center-left, center-center, center-right, bottom-left, "
            "bottom-center, bottom-right. Empty for default."
        ),
    )
    timing: str = Field(
        default="visual_first",
        description='When visual appears: "visual_first", "after_speech", or "term_sync"',
    )
    builds_on: str = Field(
        default="",
        description="If this visual extends/modifies a previous one, describe which and how",
    )


class TeachingBeat(BaseModel):
    """One coordinated moment of teaching — the atomic unit of a lesson plan."""

    beat_type: str = Field(
        description=(
            "Type of teaching moment. One of: hook, big_picture, "
            "first_principles, bridge, visual_build, explain, derive, ask, "
            "misconception, example, summarize, transition. The first three "
            "beats of every concept plan must be hook → big_picture → "
            "first_principles (mandatory Feynman arc — see system prompt)."
        ),
    )
    speech_guidance: str = Field(
        description=(
            "What to say during this beat. NOT a verbatim script — guidance for "
            "the teaching agent on content, tone, and approach. 2-4 sentences."
        ),
    )
    visual: VisualBeatAction | None = Field(
        default=None,
        description="Visual to show during this beat. None for speech-only beats.",
    )
    target_duration_seconds: int = Field(
        default=30,
        description="Approximate duration for this beat in seconds",
    )
    student_cue: str = Field(
        default="",
        description="What to watch for from students (confusion signals, questions)",
    )

    # Book-coverage USP (2026-05-27). Set ONLY when beat_type == "example".
    # Drives the BeatNarrationWriter's faithfulness / creativity branch.
    example_source: Literal["book", "extended"] | None = Field(
        default=None,
        description="`book` = faithful render of a textbook example (numbers + "
        "relationships preserved). `extended` = LLM-invented real-world "
        "example to strengthen coverage. None = not an example beat.",
    )
    book_example_ref: int | None = Field(
        default=None,
        description="Index into Topic.book_examples — populated when "
        "example_source='book' so the writer can look up the verbatim text + "
        "setup_facts. None for non-book beats.",
    )


class ChecklistItem(BaseModel):
    """One requirement the agent must satisfy before `resolve_doubt` is allowed.

    Items auto-tick when a tool listed in `auto_satisfied_by` is invoked, when
    a keyword in `keywords` appears in the agent's emitted voice, or via the
    explicit `mark_doubt_step_complete(step_index)` tool when the agent knows
    it has addressed the requirement but no auto-trigger fired.
    """

    description: str = Field(..., min_length=1, max_length=240)
    status: Literal["pending", "done"] = "pending"
    auto_satisfied_by: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class ConceptTeachingPlan(BaseModel):
    """Complete teaching strategy for one concept — output of the planning agent."""

    concept_title: str
    concept_index: int

    # Pedagogical strategy
    opening_hook: str = Field(
        description="Specific attention-grabbing opening — an analogy, question, or demonstration",
    )
    core_analogy: str = Field(
        description="The primary analogy or mental model to use throughout this concept",
    )
    prerequisite_bridge: str = Field(
        description="How to connect this concept to what was just taught — 1-2 sentences",
    )

    # Ordered teaching beats
    beats: list[TeachingBeat] = Field(
        description="Ordered sequence of teaching moments. As many as needed — but every beat must earn its place.",
    )

    # Board layout
    board_pattern: str = Field(
        description=(
            'Which teaching scenario to use. One of: "concept_intro", '
            '"derivation", "comparison", "problem_solving", "single_focus", '
            '"free_form". These map to reserved slot layouts on the slide + '
            "an expected notebook flow."
        ),
    )
    visual_narrative: str = Field(
        description=(
            "2-3 sentence description of the visual arc — how the slide "
            "diagram and the notebook working build on each other across "
            "beats to tell a story."
        ),
    )

    # Misconception defense
    likely_misconceptions: list[str] = Field(
        default_factory=list,
        description="Common student misconceptions to watch for and pre-empt (1-3 items)",
    )
    misconception_responses: list[str] = Field(
        default_factory=list,
        description="How to address each misconception if it surfaces (parallel to likely_misconceptions)",
    )

    # Understanding checkpoints
    check_questions: list[str] = Field(
        default_factory=list,
        description="Questions to ask students to verify understanding (1-3 items)",
    )
    expected_answers: list[str] = Field(
        default_factory=list,
        description="Expected correct answers (parallel to check_questions)",
    )

    # Transition
    transition_to_next: str = Field(
        default="",
        description="How to naturally bridge to the next concept — 1-2 sentences",
    )

    # Doubt-branch resolution checklist — populated only when this plan is a
    # doubt plan (`plan_doubt`). Empty for normal concept plans. The doubt
    # orchestrator gates `resolve_doubt` on every item being `done`.
    resolution_checklist: list[ChecklistItem] = Field(
        default_factory=list,
        description=(
            "Doubt-branch only. 2-4 items the agent must touch before "
            "resolve_doubt is allowed. Each item has a description and a "
            "list of `auto_satisfied_by` tool names that auto-tick the item "
            "when invoked. Leave empty for non-doubt plans."
        ),
    )

    @model_validator(mode="after")
    def _enforce_arc(self) -> ConceptTeachingPlan:
        # Doubt plans (concept_index = -1) bypass — they have a 2-3 beat
        # explain/ask/transition structure, not the Feynman arc.
        if self.concept_index < 0:
            return self
        if len(self.beats) < 3:
            raise ValueError(
                "ConceptTeachingPlan requires at least 3 beats (hook, "
                f"big_picture, first_principles); got {len(self.beats)}."
            )
        expected = ("hook", "big_picture", "first_principles")
        actual = tuple(b.beat_type for b in self.beats[:3])
        if actual != expected:
            raise ValueError(
                f"First three beats must be {expected} in order, got {actual}."
            )
        return self
