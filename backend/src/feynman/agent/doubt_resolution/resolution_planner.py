"""ResolutionPlanner — the LLM call that turns a classified doubt into a list
of `ResolutionBeat`s ready for delivery as a real-time mini-lecture.

The planner decides each beat's board work directly: it is shown the
chapter's AVAILABLE DIAGRAMS with their element semantics and, per beat,
chooses to reuse an existing diagram, generate a new one, keep the current
one, or none — plus what to write in the notebook and how to annotate. The
old free-text-intent + post-hoc `DiagramFitMatcher` step is no longer in the
planning path (kept only for back-compat until delivery is migrated).
"""

from __future__ import annotations

import json

import anthropic
import structlog
from pydantic import ValidationError

from feynman.agent.doubt_resolution.models import (
    ChapterContext,
    DoubtRecord,
    ResolutionPlan,
)
from feynman.agent.doubt_resolution.prereq_walker import walk_prereqs
from feynman.agent.doubt_resolution.prompts import PLANNER_SYSTEM
from feynman.config import settings

logger = structlog.get_logger()

_MODEL = "claude-sonnet-4-6"
_TOOL_NAME = "emit_resolution_plan"
_TOOL_DESCRIPTION = (
    "Emit the ResolutionPlan as a structured list of beats. "
    "Field constraints (1-6 beats, non-empty narration) are enforced."
)
_MAX_TOKENS = 4096
_MAX_ATTEMPTS = 2


async def plan_resolution(
    *,
    doubt_text: str,
    chapter_context: ChapterContext,
    current_topic_id: str | None = None,
    prior_doubts: list[DoubtRecord] | None = None,
    different_angle: bool = False,
    prior_resolution_summary: str = "",
    board_snapshot: dict | None = None,
) -> ResolutionPlan | None:
    """Classify + plan a doubt resolution in ONE CoT call (3-5 beats).

    The returned plan carries `.classification` — the planner reasons out the
    doubt's category first (which sets the depth) and emits it alongside the
    beats, so there's no separate classify round-trip.

    Returns None on persistent failure — caller (LectureDoubtSession) is
    responsible for the fallback path. Most callers should treat None as
    "skip this doubt with a graceful 'let me think about that' message."
    """
    last_error: str | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            plan = await _call_once(
                doubt_text=doubt_text,
                chapter_context=chapter_context,
                current_topic_id=current_topic_id,
                prior_doubts=prior_doubts or [],
                different_angle=different_angle,
                prior_resolution_summary=prior_resolution_summary,
                prior_validation_error=last_error,
                board_snapshot=board_snapshot,
            )
        except ValidationError as exc:
            last_error = str(exc)
            logger.warning(
                "resolution_planner.validation_error",
                attempt=attempt,
                error=last_error,
            )
            plan = None
        except Exception as exc:
            logger.warning(
                "resolution_planner.unexpected_exception",
                attempt=attempt,
                error=str(exc),
            )
            plan = None

        if plan is not None:
            if attempt > 0:
                logger.info("resolution_planner.recovered_on_retry")
            return plan

    logger.error("resolution_planner.final_failure", last_error=last_error)
    return None


async def _call_once(
    *,
    doubt_text: str,
    chapter_context: ChapterContext,
    current_topic_id: str | None,
    prior_doubts: list[DoubtRecord],
    different_angle: bool,
    prior_resolution_summary: str,
    prior_validation_error: str | None,
    board_snapshot: dict | None,
) -> ResolutionPlan | None:
    user_message = _build_user_message(
        doubt_text=doubt_text,
        chapter_context=chapter_context,
        current_topic_id=current_topic_id,
        prior_doubts=prior_doubts,
        different_angle=different_angle,
        prior_resolution_summary=prior_resolution_summary,
        prior_validation_error=prior_validation_error,
        board_snapshot=board_snapshot,
    )

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key or "")
    response = await client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        system=PLANNER_SYSTEM,
        messages=[{"role": "user", "content": user_message}],
        tools=[
            {
                "name": _TOOL_NAME,
                "description": _TOOL_DESCRIPTION,
                "input_schema": ResolutionPlan.model_json_schema(),
            }
        ],
        tool_choice={"type": "tool", "name": _TOOL_NAME},
    )

    for block in response.content:
        if (
            getattr(block, "type", None) == "tool_use"
            and getattr(block, "name", None) == _TOOL_NAME
        ):
            payload = block.input
            if not isinstance(payload, dict):
                logger.warning("resolution_planner.tool_input_not_dict")
                return None
            return ResolutionPlan.model_validate(payload)

    logger.warning("resolution_planner.no_tool_use_block")
    return None


def _active_diagram_from_snapshot(snapshot: dict | None) -> str:
    if not isinstance(snapshot, dict):
        return ""
    for el in snapshot.get("elements") or []:
        if isinstance(el, dict) and el.get("kind") == "diagram":
            return el.get("element_id") or ""
    return ""


def _format_visual_terms(chapter_context: ChapterContext, diagram_id: str) -> str:
    """Render the visual-index entries for the active diagram.

    Why: snapshot tells us WHICH diagram is on screen; this block tells the
    LLM WHAT each element on that diagram means (role + semantic). With both
    it can write narration that names elements students can actually point
    at — "look at the force_arrow on the block" rather than vague gestures.
    """
    entries = [
        e for e in chapter_context.visual_index if e.diagram_id == diagram_id
    ]
    if not entries:
        return ""
    lines = [f"ELEMENT SEMANTICS for active diagram ({diagram_id}):"]
    for e in entries[:12]:
        role = e.role or "(no role)"
        sem = e.semantic or "(no semantic)"
        lines.append(f"  - {e.element_id} ({role}): {sem}")
    lines.append(
        "  When you write a beat, prefer naming elements above by their "
        "element_id in `annotation_actions.target_element_id`."
    )
    return "\n".join(lines)


def _format_board_snapshot(snapshot: dict | None) -> str:
    """Render the unified-board-state snapshot as a prompt block.

    Why: the LLM otherwise has to guess what visual context the student is
    looking at. With this block it knows exactly which diagram is active and
    what notebook content has accumulated — so it can refer back to "the
    equation you wrote at line 2" without hallucinating phantom elements.
    Returns "" when no snapshot is supplied (chapter pre-feature, or first
    page hasn't closed yet).
    """
    if not isinstance(snapshot, dict):
        return ""
    elements = snapshot.get("elements") or []
    if not elements:
        return ""

    active_diagram_id = ""
    diagram_elements: list[dict] = []
    notebook_blocks: list[dict] = []
    for el in elements:
        if not isinstance(el, dict):
            continue
        kind = el.get("kind")
        if kind == "diagram":
            active_diagram_id = el.get("element_id", "") or active_diagram_id
        elif kind == "diagram_element":
            diagram_elements.append(el)
        elif kind == "notebook_block":
            notebook_blocks.append(el)

    lines: list[str] = ["CURRENTLY ON BOARD (what the student is staring at):"]
    page_index = snapshot.get("page_index")
    if page_index is not None:
        lines.append(f"  page_index: {page_index}")
    if active_diagram_id:
        lines.append(f"  active diagram: {active_diagram_id}")
    if diagram_elements:
        lines.append("  visible diagram elements:")
        for e in diagram_elements[:10]:
            role = e.get("role") or "(no role)"
            sem = (e.get("semantic") or "").strip()
            tail = f" — {sem}" if sem else ""
            lines.append(f"    - {e.get('element_id', '?')} ({role}){tail}")
    if notebook_blocks:
        lines.append("  notebook blocks already written:")
        for b in notebook_blocks[:10]:
            kind = b.get("block_type") or "TEXT"
            lines.append(f"    - {b.get('element_id', '?')} ({kind})")
    lines.append(
        "  Scope the resolution to these visible elements. Reference what "
        "the student can already see; do NOT invent elements that aren't "
        "in the lists above."
    )
    return "\n".join(lines)


def _build_user_message(
    *,
    doubt_text: str,
    chapter_context: ChapterContext,
    current_topic_id: str | None,
    prior_doubts: list[DoubtRecord],
    different_angle: bool,
    prior_resolution_summary: str,
    prior_validation_error: str | None,
    board_snapshot: dict | None,
) -> str:
    parts: list[str] = []

    if prior_validation_error:
        parts.append(
            "Your previous response failed validation:\n"
            f"  {prior_validation_error}\n"
            "Fix the offending field and emit a valid tool call."
        )

    parts.append(f"STUDENT DOUBT:\n{doubt_text}")

    # Whole-chapter topic list — the floor for `related_concept_ids` (the merged
    # call now classifies too, so it needs to see every topic it could map to).
    topic_lines = [
        f"  - {t.topic_id} ({t.section_number}): {t.topic_name}"
        for t in chapter_context.topics.values()
    ]
    if topic_lines:
        parts.append(
            "CHAPTER TOPICS (map the doubt to these ids for "
            "related_concept_ids):\n" + "\n".join(topic_lines)
        )

    current_topic = chapter_context.topic(current_topic_id)
    if current_topic:
        parts.append(
            "CURRENT TOPIC:\n"
            f"  topic_id: {current_topic.topic_id}\n"
            f"  section: {current_topic.section_number}\n"
            f"  name: {current_topic.topic_name}\n"
            f"  summary: {current_topic.summary or '(no summary available)'}"
        )

    board_block = _format_board_snapshot(board_snapshot)
    if board_block:
        parts.append(board_block)

    active_diagram_id = _active_diagram_from_snapshot(board_snapshot)
    if active_diagram_id:
        terms_block = _format_visual_terms(chapter_context, active_diagram_id)
        if terms_block:
            parts.append(terms_block)

    adjacent = chapter_context.adjacent_topics(current_topic_id, radius=1)
    if adjacent:
        adj_lines = [
            f"  - {t.section_number} {t.topic_name}: {t.summary or '(no summary)'}"
            for t in adjacent
        ]
        parts.append("ADJACENT TOPICS:\n" + "\n".join(adj_lines))

    prereqs = walk_prereqs(chapter_context, current_topic_id)
    if prereqs:
        prereq_lines = [
            f"  - {p.section_number} {p.topic_name}: {p.summary or '(no summary)'}"
            for p in prereqs
        ]
        parts.append(
            "PREREQ CHAIN (curriculum-graph traversal — concepts the current "
            "topic strictly depends on, BFS order):\n"
            + "\n".join(prereq_lines)
            + "\n  If the doubt suggests the student missed one of these, "
            "anchor the resolution there instead of restating the current "
            "topic."
        )

    if chapter_context.diagrams:
        diagram_lines = []
        for d in list(chapter_context.diagrams.values())[:15]:
            diagram_lines.append(f"  - {d.diagram_id}: {d.description[:200]}")
            elem_lines = []
            for eid, entry in list(d.dictionary.items())[:8]:
                if not isinstance(entry, dict):
                    continue
                role = entry.get("role") or ""
                sem = (entry.get("semantic") or "").strip()
                label = eid + (f" ({role})" if role else "")
                elem_lines.append(label + (f": {sem[:80]}" if sem else ""))
            if elem_lines:
                diagram_lines.append("      parts: " + "; ".join(elem_lines))
        parts.append(
            "AVAILABLE DIAGRAMS — reuse one by its EXACT id when it resolves "
            "the beat with complete clarity; otherwise generate a new one. "
            "Use the part ids/roles below to name elements in annotations:\n"
            + "\n".join(diagram_lines)
        )

    if prior_doubts:
        prior_lines = [
            f"  - [{r.classification.type.value}] {r.doubt_text}" for r in prior_doubts[-3:]
        ]
        parts.append("PRIOR DOUBTS THIS SESSION:\n" + "\n".join(prior_lines))

    if different_angle:
        parts.append(
            "RE-PLAN: the student was not satisfied with the previous "
            "framing. Pick a different angle, a different analogy, or "
            "attack the concept from the opposite side. Do not repeat:\n"
            f"  {prior_resolution_summary or '(no prior summary captured)'}"
        )

    parts.append(
        "Emit the plan via `emit_resolution_plan`. Classify FIRST, then the "
        "beats (the first beat reuses or writes — it never generates):\n"
        + json.dumps(
            {
                "classification": {
                    "type": "local_clarification",
                    "related_concept_ids": [],
                    "rationale": "one-sentence reason for the bucket",
                },
                "beats": [
                    {
                        "narration_text": (
                            "Here's the piece that's off: the ball keeps the "
                            "train's speed even after it leaves your hand."
                        ),
                        "diagram": {
                            "mode": "reuse",
                            "diagram_id": "<an exact id from AVAILABLE DIAGRAMS>",
                        },
                        "notebook_writes": [
                            {
                                "block": "step",
                                "text": "ball speed = train speed + toss speed",
                            }
                        ],
                        "annotation_actions": [
                            {
                                "action": "focus",
                                "target_element_id": "<an element id on that diagram>",
                                "text": "same curve",
                            }
                        ],
                    },
                    {
                        "narration_text": (
                            "Now from the platform, the path bends into an arc."
                        ),
                        "diagram": {
                            "mode": "generate",
                            "brief": (
                                "a ball's parabolic arc seen from the platform, "
                                "with the horizontal train-velocity component and "
                                "the vertical toss component labelled"
                            ),
                            "title": "Platform frame",
                        },
                        "notebook_writes": [],
                        "annotation_actions": [
                            {
                                "action": "focus",
                                "target_role": "trajectory",
                                "text": "the curve",
                            }
                        ],
                    },
                ]
            },
            indent=2,
        )
    )

    return "\n\n".join(parts)
