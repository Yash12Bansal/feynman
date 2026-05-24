"""Render a `ConceptTeachingPlan` into the markdown block injected into the
teaching agent's system prompt at runtime. Pure formatter — no LLM call,
no config dependency.
"""

from __future__ import annotations

from feynman_teaching_kernel.models import ConceptTeachingPlan


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
    parts.append(
        "\n**Teaching Beats** — follow this sequence, adapt to student responses:\n"
    )

    for i, beat in enumerate(teaching_plan.beats, 1):
        beat_label = beat.beat_type.upper()
        parts.append(
            f"\n**Beat {i} — {beat_label}** (~{beat.target_duration_seconds}s)"
        )
        parts.append(f"\n{beat.speech_guidance}")

        if beat.visual:
            v = beat.visual
            zone_str = f', zone="{v.zone}"' if v.zone else ""
            timing_str = f', timing="{v.timing}"' if v.timing != "visual_first" else ""
            parts.append(
                f"\n  Visual: `{v.tool}` — {v.description}{zone_str}{timing_str}"
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
            parts.append(f'\n- If student thinks: "{misconception}"')
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
            parts.append(f'\n- Ask: "{question}"')
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
