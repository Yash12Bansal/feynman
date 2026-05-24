"""Planning functions — make one Anthropic structured-output call per plan.

Callers thread `api_key` explicitly (no global config dependency) so the
kernel works from any consumer's venv. The backend `tools.py` /
`livekit/worker.py` pass `settings.anthropic_api_key`; the precompute
pipeline (Phase 4b) will pass its own key from `LLMConfig`.

The `curriculum`, `plan`, `audit`, and `prev_plan` params are duck-typed
`Any` in the kernel — they expose the surface
  - `curriculum.get_teaching_order()`, `curriculum.get_prerequisites(uid)`,
    `curriculum.concept_by_uid(uid)`, `curriculum.relationships`,
    `curriculum.concepts`, `curriculum.pre_generated_visuals`
  - `plan.total_concepts`
  - `audit.record(component, event, summary, **fields)` (or None)
  - `prev_plan: ConceptTeachingPlan | None`
that backend's `CurriculumData` / `LessonPlan` / `SessionAudit` already
satisfy. The pipeline-side adapters in Phase 4b construct duck-compatible
objects on the same surface.
"""

from __future__ import annotations

from typing import Any

import anthropic
import structlog

from feynman_teaching_kernel.models import ConceptTeachingPlan
from feynman_teaching_kernel.prompts import PLANNING_SYSTEM_PROMPT

logger = structlog.get_logger()


DEFAULT_PLANNING_MODEL = "claude-sonnet-4-20250514"


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
        parts.append(
            "\n### Prerequisites (students already know)\n- " + "\n- ".join(names)
        )

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
            parts.append(f'Transition phrase: "{prev_plan.transition_to_next}"')
        if prev_plan.beats:
            last_beat = prev_plan.beats[-1]
            parts.append(
                f"Last beat ({last_beat.beat_type}): {last_beat.speech_guidance}"
            )
        parts.append(
            "\n**Your opening_hook and prerequisite_bridge MUST continue naturally "
            "from the transition above. Don't start from scratch — pick up the thread.**"
        )
    elif prev_concept_title:
        parts.append(f"\n### Previous Concept (just finished)\n{prev_concept_title}")

    # Related concepts
    edges = [
        e
        for e in curriculum.relationships
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
        c
        for c in curriculum.concepts
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
    curriculum: Any,  # CurriculumData
    plan: Any,  # LessonPlan
    board_summary: str = "",
    audit: Any | None = None,  # SessionAudit
    prev_plan: ConceptTeachingPlan | None = None,
    allowed_visual_tools: list[str] | None = None,
    *,
    api_key: str,
    model: str = DEFAULT_PLANNING_MODEL,
) -> ConceptTeachingPlan | None:
    """Generate a ConceptTeachingPlan for the given concept index.

    `allowed_visual_tools`: when non-None, the LLM is told to restrict
    `visual.tool` for every beat to one of these names. When None (live
    agent default), no constraint is injected — behavior unchanged from
    pre-doc-18. The precompute pipeline passes a restricted list so
    concept-style beats produce diagrams the renderer can actually draw.

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

    if allowed_visual_tools:
        tool_list = ", ".join(f"`{t}`" for t in allowed_visual_tools)
        user_message += (
            "\n\n## CONSTRAINT — Visual tool whitelist\n"
            f"`visual.tool` for EVERY beat MUST be one of: {tool_list}.\n"
            "Tools outside this list are not supported by the current "
            "renderer and will be rewritten to `draw_design_diagram` by "
            "the pipeline. Plan within the whitelist from the start."
        )

    logger.info(
        "planner.generating",
        concept_index=concept_index,
        concept=concept.topic_name,
    )

    if audit:
        audit.record(
            "planner",
            "plan_started",
            f"concept={concept_index} '{concept.topic_name}'",
            concept_index=concept_index,
        )

    try:
        client = anthropic.AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model=model,
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
                # Force concept_index BEFORE model_validate — the arc validator
                # gates on this field, so it must match reality at validate time.
                if isinstance(block.input, dict):
                    block.input["concept_index"] = concept_index
                result = ConceptTeachingPlan.model_validate(block.input)
                # Ensure correct metadata (concept_index already set above)
                result.concept_title = concept.topic_name

                logger.info(
                    "planner.plan_ready",
                    concept_index=concept_index,
                    concept=concept.topic_name,
                    beats=len(result.beats),
                    pattern=result.board_pattern,
                )

                if audit:
                    audit.record(
                        "planner",
                        "plan_ready",
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
                "planner",
                "plan_failed",
                f"concept={concept_index} '{concept.topic_name}'",
                concept_index=concept_index,
            )
        return None


async def plan_doubt(
    doubt_description: str,
    parent_concept: str = "",
    board_summary: str = "",
    curriculum: Any | None = None,  # CurriculumData
    audit: Any | None = None,  # SessionAudit
    *,
    api_key: str,
    model: str = DEFAULT_PLANNING_MODEL,
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
        "\nRemember the split board: the doubt usually wants a fresh slide scene + "
        "a couple notebook lines, not a full new derivation."
        "\n"
        "\n## Resolution Checklist (REQUIRED for doubt plans)"
        "\nPopulate `resolution_checklist` with 2-4 items the agent MUST touch before "
        "calling resolve_doubt. Each item gates resolution — the orchestrator will "
        "block resolve_doubt until every item is ticked."
        "\n"
        "\nEach item has:"
        '\n- `description`: short imperative (e.g., "show diagram explaining ratio constancy", "tie back to ladder").'
        '\n- `status`: always "pending" at plan time — the orchestrator flips items to "done" as work happens.'
        "\n- `auto_satisfied_by`: list of tool names that auto-tick the item when invoked. "
        "Choose ONLY from this controlled vocabulary:"
        '\n  ["draw_design_diagram", "draw_diagram", "draw_scene", "pin_label_near", '
        '"draw_callout", "bracket", "highlight_pulse", "write_section", '
        '"write_equation", "write_step", "write_text", "show_equation"]'
        "\n- `keywords` (optional): 1-3 short tokens that the agent's voice would "
        "naturally include when satisfying this step (case-insensitive substring "
        "match). Use only for steps where the verbal answer is the work — "
        'e.g. ["ladder"] for "tie back to the original ladder problem". Leave '
        "empty when a tool call (above) already covers it."
        "\n"
        '\nExample: a doubt about "why sin = opp/hyp?" might produce:'
        '\n  1. {description: "show diagram explaining ratio constancy", '
        'auto_satisfied_by: ["draw_design_diagram", "draw_scene"], keywords: []}'
        '\n  2. {description: "explain why ratios are angle-dependent", '
        'auto_satisfied_by: ["write_step", "write_text"], keywords: ["angle", "ratio"]}'
        '\n  3. {description: "tie back to the original ladder problem", '
        'auto_satisfied_by: ["pin_label_near", "highlight_pulse"], keywords: ["ladder"]}'
        "\n"
        "\nKeep items concrete and tied to a specific tool action or keyword. Vague items "
        '("explain it well") cannot auto-tick and force the agent to use '
        "mark_doubt_step_complete manually."
    )

    user_message = "\n".join(parts)

    logger.info("planner.doubt_plan_started", doubt=doubt_description[:60])

    if audit:
        audit.record(
            "planner",
            "doubt_plan_started",
            f"doubt='{doubt_description[:60]}'",
        )

    try:
        client = anthropic.AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model=model,
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
                # Force concept_index = -1 BEFORE model_validate so the arc
                # validator skips this plan. The doubt plan has 2-3 free-form
                # beats, not the hook → big_picture → first_principles arc.
                if isinstance(block.input, dict):
                    block.input["concept_index"] = -1
                result = ConceptTeachingPlan.model_validate(block.input)
                result.concept_title = f"Doubt: {doubt_description[:50]}"
                # concept_index already set above

                logger.info(
                    "planner.doubt_plan_ready",
                    doubt=doubt_description[:60],
                    beats=len(result.beats),
                )

                if audit:
                    audit.record(
                        "planner",
                        "doubt_plan_ready",
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
                "planner",
                "doubt_plan_failed",
                f"doubt='{doubt_description[:60]}'",
            )
        return None
