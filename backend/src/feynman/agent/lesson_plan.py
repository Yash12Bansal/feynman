"""Lesson plan data models and generation via Anthropic structured output."""

from __future__ import annotations

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
