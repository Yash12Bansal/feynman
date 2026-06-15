"""Load checkpoint questions from the curriculum graph (Neo4j).

Read-only against the shared curriculum graph — independent of the student
graph. Mirrors `doubt_resolution.chapter_loader`'s driver usage.

NOTE (scale): like the rest of the backend's Neo4j access, this opens a driver
per call. A shared app-lifetime driver is the right optimisation across ALL
Neo4j callers — tracked as a cross-cutting follow-up, not specific to this
module.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from neo4j import AsyncGraphDatabase

from feynman.config import settings
from feynman.interaction.models import Question

logger = structlog.get_logger()

_RETURN = (
    "RETURN q.question_id AS question_id, q.q_text AS q_text, q.answer AS answer, "
    "q.answer_audio_url AS answer_audio_url, q.options AS options, q.type AS type, "
    "q.needs_review AS needs_review, q.linked_topic_ids AS linked_topic_ids, "
    "q.question_diagram_built AS question_diagram_built, "
    "q.question_diagram_needed AS question_diagram_needed, "
    "q.question_diagram_spec AS question_diagram_spec, "
    "q.solution_diagram_built AS solution_diagram_built, "
    "q.solution_diagram_needed AS solution_diagram_needed, "
    "q.solution_diagram_spec AS solution_diagram_spec, "
    "q.solution_steps AS solution_steps"
)
_LOAD_TOPIC_QUESTIONS = (
    "MATCH (t:Topic {topic_id: $topic_id})-[:HAS_QUESTION]->(q:Question) "
    f"{_RETURN} ORDER BY q.question_id"
)
_LOAD_QUESTION = "MATCH (q:Question {question_id: $question_id}) " + _RETURN


async def _run(cypher: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            result = await session.run(cypher, params)
            return [record.data() async for record in result]
    finally:
        await driver.close()


def _to_question(row: dict[str, Any], topic_id: str = "") -> Question:
    raw_type = row.get("type") or "mcq"
    q_type = raw_type if raw_type in ("mcq", "solved_example") else "mcq"
    linked = row.get("linked_topic_ids") or []
    return Question(
        question_id=row["question_id"],
        topic_id=topic_id or (linked[0] if linked else ""),
        type=q_type,
        q_text=row.get("q_text") or "",
        options=list(row.get("options") or []),
        answer=row.get("answer") or "",
        answer_audio_url=row.get("answer_audio_url"),
        needs_review=bool(row.get("needs_review")),
        question_diagram_built=bool(row.get("question_diagram_built")),
        question_diagram_needed=bool(row.get("question_diagram_needed")),
        question_diagram_spec=_parse_spec(row.get("question_diagram_spec")),
        solution_diagram_built=bool(row.get("solution_diagram_built")),
        solution_diagram_needed=bool(row.get("solution_diagram_needed")),
        solution_diagram_spec=_parse_spec(row.get("solution_diagram_spec")),
        solution_steps=list(row.get("solution_steps") or []),
    )


def _parse_spec(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def load_topic_questions(topic_id: str) -> list[Question]:
    """Every question linked to a topic, in a stable order."""
    rows = await _run(_LOAD_TOPIC_QUESTIONS, {"topic_id": topic_id})
    return [_to_question(r, topic_id) for r in rows]


async def load_question(question_id: str) -> Question | None:
    """One question by id, including its answer (server-side grading)."""
    rows = await _run(_LOAD_QUESTION, {"question_id": question_id})
    return _to_question(rows[0]) if rows else None


async def _cache_diagram(
    question_id: str,
    *,
    prefix: str,
    diagram_needed: bool,
    diagram_spec: dict[str, Any] | None,
    steps: list[str] | None = None,
) -> None:
    """Persist a generated diagram on the Question node (curriculum graph —
    shared, so every future student reuses it; the LLM runs once). `prefix` is
    'question' or 'solution'. `steps` (solution only) is the worked-solution
    step list, cached alongside so the reveal is generated once too."""
    set_steps = ", q.solution_steps = $steps" if steps is not None else ""
    await _run(
        f"MATCH (q:Question {{question_id: $question_id}}) "
        f"SET q.{prefix}_diagram_built = true, "
        f"q.{prefix}_diagram_needed = $needed, "
        f"q.{prefix}_diagram_spec = $spec"
        f"{set_steps}",
        {
            "question_id": question_id,
            "needed": diagram_needed,
            "spec": json.dumps(diagram_spec) if diagram_spec else None,
            "steps": steps,
        },
    )


async def cache_solution_diagram(
    question_id: str,
    *,
    diagram_needed: bool,
    diagram_spec: dict[str, Any] | None,
    steps: list[str] | None = None,
) -> None:
    await _cache_diagram(
        question_id,
        prefix="solution",
        diagram_needed=diagram_needed,
        diagram_spec=diagram_spec,
        steps=steps,
    )


async def cache_question_diagram(
    question_id: str, *, diagram_needed: bool, diagram_spec: dict[str, Any] | None
) -> None:
    await _cache_diagram(
        question_id, prefix="question", diagram_needed=diagram_needed, diagram_spec=diagram_spec
    )
