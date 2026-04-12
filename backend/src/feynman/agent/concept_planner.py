"""Planning agent — generates structured teaching plans per concept.

Runs ASYNC while teaching the previous concept. The output (ConceptTeachingPlan)
replaces raw key_points in the teaching prompt, giving the teaching agent a
deliberate pedagogical strategy instead of "figure it out from bullet points."

Two-agent architecture:
  Planning Agent (this module)  → ConceptTeachingPlan (structured beats)
  Teaching Agent (prompts + LLM) → natural speech + tool calls following the plan
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import anthropic
import structlog
from pydantic import BaseModel, Field

from feynman.config import settings

if TYPE_CHECKING:
    from feynman.agent.curriculum_loader import CurriculumData, CurriculumConcept
    from feynman.agent.lesson_plan import LessonPlan
    from feynman.agent.session_audit import SessionAudit

logger = structlog.get_logger()


# ── Data Models ─────────────────────────────────────────────


class VisualBeatAction(BaseModel):
    """A specific visual tool call planned for a teaching beat."""

    tool: str = Field(
        description=(
            "Which visual tool to use. One of: show_text, show_equation, "
            "step_equation, draw_design_diagram, draw_scene, draw_diagram, "
            "show_graph, highlight_diagram_part, annotate"
        ),
    )
    description: str = Field(
        description="What this visual shows — used as the tool's main content parameter",
    )
    zone: str = Field(
        default="",
        description=(
            "Board zone for placement. One of: top-left, top-center, top-right, "
            "center-left, center-center, center-right, bottom-left, bottom-center, "
            "bottom-right. Empty for default."
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
            "Type of teaching moment. One of: hook, bridge, visual_build, "
            "explain, derive, ask, misconception, example, summarize, transition"
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
            'Which board layout pattern to use. One of: "concept_intro", '
            '"derivation", "comparison", "problem_solving", "single_equation_focus"'
        ),
    )
    visual_narrative: str = Field(
        description=(
            "2-3 sentence description of the visual arc — how visuals build "
            "on each other across beats to tell a story"
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


# ── Planning Agent ──────────────────────────────────────────


PLANNING_SYSTEM_PROMPT = """\
You are an expert lesson planning agent for a classroom AI teacher called Feynman.

Your job: given a concept from a curriculum knowledge graph, produce a teaching plan \
that a real-time teaching agent will follow. You are NOT the teacher — you are the \
teacher's lesson planner.

Think like an experienced educator:
- How would a master teacher introduce this concept?
- What analogy makes it click for a 15-year-old?
- What visual sequence builds understanding incrementally?
- What misconceptions will students have? How to pre-empt them?
- What question checks if they actually understood?

## Style: Concise, Interactive, Engaging

This is a real classroom. The plan should feel like a conversation, not a lecture. \
Every beat should either build understanding or check it — no filler.

- **Concise**: Every beat must earn its place. If students can understand something \
from the visual alone, combine visual + explain into one beat. Don't pad.
- **Interactive**: Plan moments where students THINK — predict, answer, discuss. \
Passive listening kills attention. One good question beats two explanation beats.
- **Engaging**: Lead with curiosity, not definitions. Use analogies students can feel. \
Make the visual the star — the speech supports the visual, not the other way around.
- **Speech guidance**: Keep it to 1-2 sentences of direction. The teaching agent \
will expand naturally — don't over-script.

## Planning Principles

1. **Hook first**: Every concept needs an attention-grabber — a surprising fact, \
a relatable analogy, or a provocative question. Never start with a definition.

2. **Visual narrative**: Plan visuals that BUILD on each other — don't just show \
a finished diagram. Start simple, add layers as you explain.

3. **One idea per beat**: Each beat should teach ONE thing. Don't cram multiple \
ideas into a single beat.

4. **Ask before telling**: Plan beats where you ask students to PREDICT before \
revealing the answer. This activates prior knowledge and creates curiosity.

5. **Misconception pre-emption**: Don't wait for confusion — plan a beat that \
explicitly addresses the most common mistakes BEFORE students make them.

6. **Incremental visuals**: Prefer draw_scene (instant) for physics/chemistry/geometry. \
Use draw_design_diagram only for complex illustrations. Use show_equation for math. \
Use step_equation for derivations. Plan the zone layout.

7. **Concrete before abstract**: Always show a concrete example or visual BEFORE \
the formula. Formula should explain what they already see, not introduce new ideas.

## Available Visual Tools

- show_text: Key points, definitions, summaries
- show_equation: Single LaTeX equation (supports term_by_term animation)
- step_equation: Multi-step derivation with progressive reveal
- draw_scene: Physics/chemistry scenes from component library (INSTANT — prefer this)
  - scene_type: "free_body", "optics", "circuit", "geometry", "chemistry"
- draw_design_diagram: AI-generated SVG diagram (5-15s, use ONLY when pre-rendered or \
when draw_scene can't handle it)
- draw_diagram: Flowcharts, concept maps (auto-layout)
- show_graph: Line/bar/scatter/function plots
- highlight_diagram_part: Spotlight parts of an existing diagram
- annotate: Circle, underline, arrow (ephemeral markup)

## Board Layout Patterns

- concept_intro: Diagram center-left, equation center-right, title top-center
- derivation: Starting equation top-center, steps flowing down center, result bottom
- comparison: Case A left column, Case B right column, shared insight bottom-center
- problem_solving: Given/Find top-right, diagram center-left, solution center-right
- single_equation_focus: One big equation center-center, nothing else competing

Be specific in speech_guidance — don't say "explain the concept", say "use the \
ball-on-hill analogy: PE at top converts to KE at bottom, just like spring PE \
converts to KE at equilibrium."
"""


def _build_planning_context(
    concept: Any,  # CurriculumConcept
    concept_index: int,
    curriculum: Any,  # CurriculumData
    plan: Any,  # LessonPlan
    prev_concept_title: str = "",
    next_concept_title: str = "",
    board_summary: str = "",
    prev_plan: ConceptTeachingPlan | None = None,
) -> str:
    """Build the user message for the planning agent."""
    parts: list[str] = []

    parts.append(f"## Concept to Plan: {concept.topic_name}")
    parts.append(f"Concept index: {concept_index + 1} of {plan.total_concepts}")
    parts.append(f"Type: {concept.concept_type}")
    parts.append(f"Difficulty: {concept.difficulty}")

    if concept.summary:
        parts.append(f"\n### Teaching Content\n{concept.summary}")

    if concept.source_text:
        parts.append(f"\n### Source Text (from textbook)\n{concept.source_text[:600]}")

    if concept.visual_hint:
        parts.append(f"\n### Visual Hint\n{concept.visual_hint}")

    # Prerequisites
    prereqs = curriculum.get_prerequisites(concept.uid)
    if prereqs:
        names = [p.topic_name for p in prereqs[:5]]
        parts.append(f"\n### Prerequisites (students already know)\n- " + "\n- ".join(names))

    # What comes next (for transition planning)
    is_last_concept = concept_index + 1 >= plan.total_concepts
    if is_last_concept:
        parts.append(
            "\n### THIS IS THE LAST CONCEPT"
            "\nAfter this, the lesson is complete. Your transition_to_next should "
            "wrap up the entire lesson — summarize the key thread across all concepts, "
            "leave students with a takeaway or a curiosity question to think about. "
            "Do NOT bridge to a next concept that doesn't exist."
        )
    elif next_concept_title:
        parts.append(f"\n### Next Concept\n{next_concept_title}")

    # What was just taught — rich context from previous plan for continuity
    if prev_plan:
        parts.append(f"\n### Previous Concept: {prev_plan.concept_title}")
        parts.append(f"Analogy used: {prev_plan.core_analogy}")
        if prev_plan.transition_to_next:
            parts.append(f"Transition phrase: \"{prev_plan.transition_to_next}\"")
        if prev_plan.beats:
            last_beat = prev_plan.beats[-1]
            parts.append(f"Last beat ({last_beat.beat_type}): {last_beat.speech_guidance}")
        parts.append(
            "\n**Your opening_hook and prerequisite_bridge MUST continue naturally "
            "from the transition above. Don't start from scratch — pick up the thread.**"
        )
    elif prev_concept_title:
        parts.append(f"\n### Previous Concept (just finished)\n{prev_concept_title}")

    # Related concepts
    edges = [
        e for e in curriculum.relationships
        if e.from_uid == concept.uid or e.to_uid == concept.uid
    ]
    if edges:
        parts.append("\n### Related Concepts")
        for edge in edges[:8]:
            other_uid = edge.to_uid if edge.from_uid == concept.uid else edge.from_uid
            other = curriculum.concept_by_uid(other_uid)
            name = other.topic_name if other else other_uid
            parts.append(f"- {edge.rel_type}: {name}")

    # Detail nodes (sub-topics to cover)
    details = [
        c for c in curriculum.concepts
        if c.level == 1
        and any(
            e.from_uid == concept.uid and e.to_uid == c.uid
            for e in curriculum.relationships
        )
    ]
    if details:
        parts.append("\n### Sub-topics to cover")
        for d in details[:6]:
            parts.append(f"- [{d.concept_type}] {d.topic_name}")

    # Board context
    if board_summary:
        parts.append(f"\n### Current Board State\n{board_summary}")

    # Pre-generated visuals available
    if concept.uid in curriculum.pre_generated_visuals:
        parts.append(
            "\n### Pre-rendered Visual Available\n"
            "A diagram has been pre-generated for this concept. "
            "Plan a beat that uses draw_design_diagram — it will render instantly."
        )

    return "\n".join(parts)


async def plan_concept(
    concept_index: int,
    curriculum: CurriculumData,
    plan: LessonPlan,
    board_summary: str = "",
    audit: SessionAudit | None = None,
    prev_plan: ConceptTeachingPlan | None = None,
) -> ConceptTeachingPlan | None:
    """Generate a ConceptTeachingPlan for the given concept index.

    Makes one Anthropic structured output call. Returns None on failure
    (the teaching agent falls back to the current unplanned behavior).
    """
    teaching_order = curriculum.get_teaching_order()
    concept_level = [c for c in teaching_order if c.level == 0]

    if concept_index >= len(concept_level):
        return None

    concept = concept_level[concept_index]

    # Context for the planning agent
    prev_title = ""
    next_title = ""
    if concept_index > 0 and concept_index - 1 < len(concept_level):
        prev_title = concept_level[concept_index - 1].topic_name
    if concept_index + 1 < len(concept_level):
        next_title = concept_level[concept_index + 1].topic_name

    user_message = _build_planning_context(
        concept=concept,
        concept_index=concept_index,
        curriculum=curriculum,
        plan=plan,
        prev_concept_title=prev_title,
        next_concept_title=next_title,
        board_summary=board_summary,
        prev_plan=prev_plan,
    )

    logger.info(
        "planner.generating",
        concept_index=concept_index,
        concept=concept.topic_name,
    )

    if audit:
        audit.record(
            "planner", "plan_started",
            f"concept={concept_index} '{concept.topic_name}'",
            concept_index=concept_index,
        )

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=PLANNING_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            tools=[
                {
                    "name": "create_teaching_plan",
                    "description": "Create a structured teaching plan for this concept.",
                    "input_schema": ConceptTeachingPlan.model_json_schema(),
                }
            ],
            tool_choice={"type": "tool", "name": "create_teaching_plan"},
        )

        for block in response.content:
            if block.type == "tool_use" and block.name == "create_teaching_plan":
                result = ConceptTeachingPlan.model_validate(block.input)
                # Ensure correct metadata
                result.concept_title = concept.topic_name
                result.concept_index = concept_index

                logger.info(
                    "planner.plan_ready",
                    concept_index=concept_index,
                    concept=concept.topic_name,
                    beats=len(result.beats),
                    pattern=result.board_pattern,
                )

                if audit:
                    audit.record(
                        "planner", "plan_ready",
                        f"concept={concept_index} beats={len(result.beats)} "
                        f"pattern='{result.board_pattern}'",
                        concept_index=concept_index,
                        beat_count=len(result.beats),
                    )

                return result

        logger.warning("planner.no_tool_call", concept_index=concept_index)
        return None

    except Exception:
        logger.warning(
            "planner.generation_failed",
            concept_index=concept_index,
            concept=concept.topic_name,
            exc_info=True,
        )
        if audit:
            audit.record(
                "planner", "plan_failed",
                f"concept={concept_index} '{concept.topic_name}'",
                concept_index=concept_index,
            )
        return None


async def plan_doubt(
    doubt_description: str,
    parent_concept: str = "",
    board_summary: str = "",
    curriculum: CurriculumData | None = None,
    audit: SessionAudit | None = None,
) -> ConceptTeachingPlan | None:
    """Generate a teaching plan for a student doubt.

    Lighter than concept planning — produces 3-5 focused beats to address
    the confusion and bridge back to the main lesson.
    """
    parts = [
        "## Student Doubt to Address",
        f"The student is confused about: {doubt_description}",
    ]
    if parent_concept:
        parts.append(f"\nThis came up while teaching: {parent_concept}")
    if board_summary:
        parts.append(f"\n### Current Board\n{board_summary}")

    parts.append(
        "\n## Instructions"
        "\nPlan 2-3 focused beats to address this doubt. This is a 60-90 second detour, "
        "NOT a new lesson:"
        "\n1. Re-explain using a different angle/analogy (beat_type: explain or visual_build)"
        "\n2. Check understanding with one question (beat_type: ask)"
        "\n3. Bridge back to main lesson (beat_type: transition)"
        "\nDo NOT over-explain. One good analogy beats three mediocre explanations."
    )

    user_message = "\n".join(parts)

    logger.info("planner.doubt_plan_started", doubt=doubt_description[:60])

    if audit:
        audit.record(
            "planner", "doubt_plan_started",
            f"doubt='{doubt_description[:60]}'",
        )

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            system=PLANNING_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            tools=[
                {
                    "name": "create_teaching_plan",
                    "description": "Create a focused teaching plan for this student doubt.",
                    "input_schema": ConceptTeachingPlan.model_json_schema(),
                }
            ],
            tool_choice={"type": "tool", "name": "create_teaching_plan"},
        )

        for block in response.content:
            if block.type == "tool_use" and block.name == "create_teaching_plan":
                result = ConceptTeachingPlan.model_validate(block.input)
                result.concept_title = f"Doubt: {doubt_description[:50]}"
                result.concept_index = -1

                logger.info(
                    "planner.doubt_plan_ready",
                    doubt=doubt_description[:60],
                    beats=len(result.beats),
                )

                if audit:
                    audit.record(
                        "planner", "doubt_plan_ready",
                        f"doubt='{doubt_description[:60]}' beats={len(result.beats)}",
                    )

                return result

        return None

    except Exception:
        logger.warning(
            "planner.doubt_plan_failed",
            doubt=doubt_description[:60],
            exc_info=True,
        )
        if audit:
            audit.record(
                "planner", "doubt_plan_failed",
                f"doubt='{doubt_description[:60]}'",
            )
        return None


def format_plan_for_prompt(teaching_plan: ConceptTeachingPlan) -> str:
    """Format a ConceptTeachingPlan into a prompt section for the teaching agent.

    This replaces the raw key_points + visual_suggestions in build_teaching_prompt().
    """
    parts: list[str] = []

    parts.append(f"\n### Teaching Plan for: {teaching_plan.concept_title}\n")

    parts.append(f"**Board pattern**: {teaching_plan.board_pattern}\n")
    parts.append(f"**Core analogy**: {teaching_plan.core_analogy}\n")

    if teaching_plan.prerequisite_bridge:
        parts.append(f"**Bridge from previous**: {teaching_plan.prerequisite_bridge}\n")

    parts.append(f"\n**Visual narrative**: {teaching_plan.visual_narrative}\n")

    # Beats — the main content
    parts.append("\n**Teaching Beats** — follow this sequence, adapt to student responses:\n")

    for i, beat in enumerate(teaching_plan.beats, 1):
        beat_label = beat.beat_type.upper()
        parts.append(f"\n**Beat {i} — {beat_label}** (~{beat.target_duration_seconds}s)")
        parts.append(f"\n{beat.speech_guidance}")

        if beat.visual:
            v = beat.visual
            zone_str = f', zone="{v.zone}"' if v.zone else ""
            timing_str = f', timing="{v.timing}"' if v.timing != "visual_first" else ""
            parts.append(
                f'\n  Visual: `{v.tool}` — {v.description}{zone_str}{timing_str}'
            )
            if v.builds_on:
                parts.append(f"\n  (Builds on: {v.builds_on})")

        if beat.student_cue:
            parts.append(f"\n  Watch for: {beat.student_cue}")

        parts.append("")  # blank line between beats

    # Misconceptions
    if teaching_plan.likely_misconceptions:
        parts.append("\n**Misconceptions to watch for:**")
        for misconception, response in zip(
            teaching_plan.likely_misconceptions,
            teaching_plan.misconception_responses,
            strict=False,
        ):
            parts.append(f"\n- If student thinks: \"{misconception}\"")
            if response:
                parts.append(f"  → Response: {response}")

    # Check questions
    if teaching_plan.check_questions:
        parts.append("\n**Understanding checks:**")
        for question, answer in zip(
            teaching_plan.check_questions,
            teaching_plan.expected_answers,
            strict=False,
        ):
            parts.append(f"\n- Ask: \"{question}\"")
            if answer:
                parts.append(f"  Expected: {answer}")

    # Transition
    if teaching_plan.transition_to_next:
        parts.append(f"\n**Transition to next**: {teaching_plan.transition_to_next}")

    parts.append(
        "\n\n**IMPORTANT**: This plan is guidance, not a rigid script. "
        "Keep it concise and interactive — read the room. "
        "If students get it quickly, skip ahead. If they're confused, spend more time. "
        "Adapt to student energy, not the plan. "
        "Call advance_concept() when the key ideas have landed.\n"
    )

    return "\n".join(parts)
