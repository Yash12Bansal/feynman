"""Lesson plan data models and generation via Anthropic structured output."""

from __future__ import annotations

import re
from typing import Any

import anthropic
import structlog
from pydantic import BaseModel

from feynman.common.types import Subject
from feynman.config import settings

logger = structlog.get_logger()


class ConceptNode(BaseModel):
    """A single concept to teach within a lesson."""

    title: str
    description: str
    key_points: list[str]
    visual_suggestions: list[str]
    estimated_minutes: float = 5.0


class LessonPlan(BaseModel):
    """Ordered sequence of concepts for a teaching session."""

    topic: str
    subject: Subject | None = None
    grade_level: str = ""
    objective: str
    concepts: list[ConceptNode]

    def concept_at(self, index: int) -> ConceptNode | None:
        if 0 <= index < len(self.concepts):
            return self.concepts[index]
        return None

    @property
    def total_concepts(self) -> int:
        return len(self.concepts)


LESSON_PLAN_PROMPT = """\
You are a curriculum designer for a classroom AI teacher. Given a topic, create a \
structured lesson plan that breaks the topic into a clear sequence of concepts.

Rules:
- Create 4-8 concepts in logical teaching order (foundations first, build up)
- Each concept should take roughly 3-7 minutes to teach
- Key points: 3-5 things the student should understand after this concept
- Visual suggestions: what visual tools would help (equations, diagrams, graphs, step-by-step solutions)
- The description is a 1-2 sentence teaching objective, NOT the content itself
- Think like a great teacher: what order builds understanding brick by brick?
"""


async def generate_lesson_plan(
    topic: str,
    subject: Subject | None = None,
    grade_level: str = "",
) -> LessonPlan:
    """Generate a structured lesson plan using Anthropic structured output.

    Uses the raw Anthropic SDK (not the LiveKit LLM plugin) because this is
    a one-shot planning call, not part of the voice pipeline.
    """
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    user_message = f"Topic: {topic}"
    if subject:
        user_message += f"\nSubject: {subject.value}"
    if grade_level:
        user_message += f"\nGrade level: {grade_level}"

    logger.info("lesson_plan.generating", topic=topic, subject=subject, grade_level=grade_level)

    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=LESSON_PLAN_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        tools=[
            {
                "name": "create_lesson_plan",
                "description": "Create a structured lesson plan.",
                "input_schema": LessonPlan.model_json_schema(),
            }
        ],
        tool_choice={"type": "tool", "name": "create_lesson_plan"},
    )

    # Extract the tool use block containing the structured output
    for block in response.content:
        if block.type == "tool_use" and block.name == "create_lesson_plan":
            plan = LessonPlan.model_validate(block.input)
            # Override with the actual values passed in (LLM might alter them)
            plan.topic = topic
            plan.subject = subject
            plan.grade_level = grade_level
            logger.info(
                "lesson_plan.generated",
                topic=topic,
                num_concepts=plan.total_concepts,
            )
            return plan

    # Fallback — should never happen with tool_choice=tool
    msg = "LLM did not return a lesson plan tool call"
    raise RuntimeError(msg)


# ── ConceptGraph → LessonPlan conversion ─────────────────


_VISUAL_KEYWORDS = re.compile(
    r"\b(diagram|figure|draw|illustrat|sketch|apparatus|setup|circuit|"
    r"ray|cross[- ]section|arrangement|schematic)\b",
    re.IGNORECASE,
)


def _extract_key_points_from_node(node: Any) -> list[str]:
    """Extract 3-5 key points from a ConceptGraph node's summary."""
    summary = node.summary or ""
    # Split on sentence boundaries and pick first 5 substantial sentences.
    sentences = [s.strip() for s in re.split(r"[.!?]+", summary) if len(s.strip()) > 20]
    return sentences[:5] if sentences else [summary[:200]]


def _extract_visual_suggestions_from_node(node: Any, graph: Any) -> list[str]:
    """Extract visual suggestions from a ConceptGraph node.

    Scans the node's summary for visual/spatial descriptions and generates
    specific suggestions based on content. More specific than runtime LLM
    generation because we have the actual textbook content.
    """
    suggestions: list[str] = []
    summary = node.summary or ""
    topic = node.topic_name or ""

    # Check if summary describes spatial/visual content.
    if _VISUAL_KEYWORDS.search(summary):
        suggestions.append(f"Draw detailed diagram for {topic}")

    # Check for equations/formulas in the content.
    if re.search(r"[=∝∞∫∑]|\\frac|\\sqrt|formula|equation", summary):
        suggestions.append(f"Show key equation for {topic}")

    # Check for step-by-step processes.
    if re.search(r"\bstep\b|\bfirst\b.*\bthen\b|\bprocess\b|\bderivation\b", summary, re.IGNORECASE):
        suggestions.append(f"Step-by-step derivation for {topic}")

    # Check for comparisons.
    if re.search(r"\bvs\b|\bcompare|\bcontrast|\bdifference\b|\bsimilar\b", summary, re.IGNORECASE):
        suggestions.append(f"Comparison diagram for {topic}")

    # If nothing visual detected, add a generic suggestion.
    if not suggestions:
        suggestions.append(f"Visual aid for {topic}")

    return suggestions


def _estimate_time_from_node(node: Any) -> float:
    """Estimate teaching time in minutes from summary length and depth."""
    summary_len = len(node.summary or "")
    # Rough heuristic: ~1 min per 200 chars of content, clamped 3-10 min.
    estimated = max(3.0, min(10.0, summary_len / 200))
    # Deeper nodes tend to be shorter to teach.
    if node.level > 0:
        estimated *= 0.7
    return round(estimated, 1)


def lesson_plan_from_graph(
    graph: Any,
    grade_level: str = "",
    subject: Subject | None = None,
) -> LessonPlan:
    """Derive a LessonPlan from a pre-computed ConceptGraph.

    Maps graph teaching order → LessonPlan concept sequence.
    Uses node summaries for richer visual_suggestions than runtime LLM generation.

    Only includes top-level (level 0) and first-level (level 1) nodes.
    Deeper sub-topics are folded into their parent's key_points.
    """
    teaching_order = graph.get_teaching_order()
    concepts: list[ConceptNode] = []

    for node in teaching_order:
        if node.level > 1:
            continue  # fold deeper nodes into parent

        concepts.append(ConceptNode(
            title=node.topic_name,
            description=node.summary[:200] if node.summary else node.topic_name,
            key_points=_extract_key_points_from_node(node),
            visual_suggestions=_extract_visual_suggestions_from_node(node, graph),
            estimated_minutes=_estimate_time_from_node(node),
        ))

    plan = LessonPlan(
        topic=graph.chapter_title,
        subject=subject,
        grade_level=grade_level,
        objective=f"Teach {graph.chapter_title}",
        concepts=concepts,
    )
    logger.info(
        "lesson_plan.from_graph",
        chapter=graph.chapter_title,
        num_concepts=len(concepts),
        graph_nodes=len(graph.nodes),
    )
    return plan
