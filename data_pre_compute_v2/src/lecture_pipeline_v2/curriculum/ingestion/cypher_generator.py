"""Deterministic Cypher generation for v2 schema.

Produces parameterised MERGE statements for Chapter / Topic / Diagram / Question
nodes and the 5 edge types. All scalar values are parameterised — no string
interpolation into queries.

Order: Chapter nodes → Topic nodes → Diagram nodes → Question nodes → edges
(CONTAINS, NEXT, PREREQ, HAS_DIAGRAM, HAS_QUESTION). Hierarchy-first ordering
guarantees MATCH endpoints exist before edges reference them.

Idempotent re-runs are safe — every statement uses MERGE.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from ..models import (
    Chapter,
    CurriculumExtractionResult,
    Diagram,
    Question,
    Topic,
)

logger = logging.getLogger(__name__)


@dataclass
class CypherStatement:
    query: str
    params: dict[str, Any]
    category: str
    uid: str


class CypherGenerator:
    """Pure: same input → same output, deterministic ordering."""

    def generate(self, extraction: CurriculumExtractionResult) -> list[CypherStatement]:
        statements: list[CypherStatement] = []

        for chapter in sorted(extraction.chapters, key=lambda c: c.chapter_index):
            statements.append(self._chapter_node(chapter))

        topics_sorted = sorted(extraction.topics, key=lambda t: t.topic_id)
        for topic in topics_sorted:
            statements.append(self._topic_node(topic))

        for diagram in sorted(extraction.diagrams, key=lambda d: d.diagram_id):
            statements.append(self._diagram_node(diagram))

        for question in sorted(extraction.questions, key=lambda q: q.question_id):
            statements.append(self._question_node(question))

        for chapter in sorted(extraction.chapters, key=lambda c: c.chapter_index):
            for topic_id in chapter.topic_ids:
                statements.append(self._contains_edge(chapter.chapter_id, topic_id))

        for topic in topics_sorted:
            if topic.next_topic_id:
                statements.append(self._next_edge(topic.topic_id, topic.next_topic_id))
            for pid in sorted(topic.prereq_topic_ids):
                statements.append(self._prereq_edge(topic.topic_id, pid))
            for did in sorted(topic.has_diagram_ids):
                statements.append(self._has_diagram_edge(topic.topic_id, did))
            for qid in sorted(topic.has_question_ids):
                statements.append(self._has_question_edge(topic.topic_id, qid))

        return statements

    @staticmethod
    def _chapter_node(c: Chapter) -> CypherStatement:
        params = {
            "chapter_id": c.chapter_id,
            "chapter_index": c.chapter_index,
            "title": c.title,
            "summary": c.summary,
            "page_start": c.page_start,
            "page_end": c.page_end,
            "topic_ids": list(c.topic_ids),
            "chapter_manifest": c.chapter_manifest.model_dump_json(),
            "narration_text": c.narration_text,
            "embedding": list(c.embedding) if c.embedding else None,
            "language": c.language,
            "version": c.version,
        }
        query = (
            "MERGE (n:Chapter {chapter_id: $chapter_id})\n"
            "SET n.chapter_index = $chapter_index,\n"
            "    n.title = $title,\n"
            "    n.summary = $summary,\n"
            "    n.page_start = $page_start,\n"
            "    n.page_end = $page_end,\n"
            "    n.topic_ids = $topic_ids,\n"
            "    n.chapter_manifest = $chapter_manifest,\n"
            "    n.narration_text = $narration_text,\n"
            "    n.embedding = $embedding,\n"
            "    n.language = $language,\n"
            "    n.version = $version,\n"
            "    n.updated_at = datetime()"
        )
        return CypherStatement(query, params, "node", c.chapter_id)

    @staticmethod
    def _topic_node(t: Topic) -> CypherStatement:
        params = {
            "topic_id": t.topic_id,
            "chapter_id": t.chapter_id,
            "section_number": t.section_number,
            "within_chapter_order": t.within_chapter_order,
            "topic_name": t.topic_name,
            "orig_book_content": t.orig_book_content,
            "our_understanding": t.our_understanding,
            "examples": list(t.examples),
            "next_topic_id": t.next_topic_id,
            "prereq_topic_ids": list(t.prereq_topic_ids),
            "has_diagram_ids": list(t.has_diagram_ids),
            "has_question_ids": list(t.has_question_ids),
            "standalone_manifest": t.standalone_manifest.model_dump_json(),
            "standalone_narration_text": t.standalone_narration_text,
            "embedding": list(t.embedding) if t.embedding else None,
            "needs_review": t.needs_review,
            "language": t.language,
            "version": t.version,
        }
        query = (
            "MERGE (n:Topic {topic_id: $topic_id})\n"
            "SET n.chapter_id = $chapter_id,\n"
            "    n.section_number = $section_number,\n"
            "    n.within_chapter_order = $within_chapter_order,\n"
            "    n.topic_name = $topic_name,\n"
            "    n.orig_book_content = $orig_book_content,\n"
            "    n.our_understanding = $our_understanding,\n"
            "    n.examples = $examples,\n"
            "    n.next_topic_id = $next_topic_id,\n"
            "    n.prereq_topic_ids = $prereq_topic_ids,\n"
            "    n.has_diagram_ids = $has_diagram_ids,\n"
            "    n.has_question_ids = $has_question_ids,\n"
            "    n.standalone_manifest = $standalone_manifest,\n"
            "    n.standalone_narration_text = $standalone_narration_text,\n"
            "    n.embedding = $embedding,\n"
            "    n.needs_review = $needs_review,\n"
            "    n.language = $language,\n"
            "    n.version = $version,\n"
            "    n.updated_at = datetime()"
        )
        return CypherStatement(query, params, "node", t.topic_id)

    @staticmethod
    def _diagram_node(d: Diagram) -> CypherStatement:
        params = {
            "diagram_id": d.diagram_id,
            "renderer": d.renderer.value,
            "render_data": json.dumps(d.render_data),
            "description": d.description,
            "fallback_image_url": d.fallback_image_url,
            "linked_topic_ids": list(d.linked_topic_ids),
            "version": d.version,
        }
        query = (
            "MERGE (n:Diagram {diagram_id: $diagram_id})\n"
            "SET n.renderer = $renderer,\n"
            "    n.render_data = $render_data,\n"
            "    n.description = $description,\n"
            "    n.fallback_image_url = $fallback_image_url,\n"
            "    n.linked_topic_ids = $linked_topic_ids,\n"
            "    n.version = $version,\n"
            "    n.updated_at = datetime()"
        )
        return CypherStatement(query, params, "node", d.diagram_id)

    @staticmethod
    def _question_node(q: Question) -> CypherStatement:
        params = {
            "question_id": q.question_id,
            "q_text": q.q_text,
            "q_audio_url": q.q_audio_url,
            "q_diagram_id": q.q_diagram_id,
            "answer": q.answer,
            "answer_audio_url": q.answer_audio_url,
            "options": list(q.options),
            "type": q.type.value,
            "source": q.source.value,
            "solution_confidence": q.solution_confidence,
            "linked_topic_ids": list(q.linked_topic_ids),
            "needs_review": q.needs_review,
            "language": q.language,
            "version": q.version,
        }
        query = (
            "MERGE (n:Question {question_id: $question_id})\n"
            "SET n.q_text = $q_text,\n"
            "    n.q_audio_url = $q_audio_url,\n"
            "    n.q_diagram_id = $q_diagram_id,\n"
            "    n.answer = $answer,\n"
            "    n.answer_audio_url = $answer_audio_url,\n"
            "    n.options = $options,\n"
            "    n.type = $type,\n"
            "    n.source = $source,\n"
            "    n.solution_confidence = $solution_confidence,\n"
            "    n.linked_topic_ids = $linked_topic_ids,\n"
            "    n.needs_review = $needs_review,\n"
            "    n.language = $language,\n"
            "    n.version = $version,\n"
            "    n.updated_at = datetime()"
        )
        return CypherStatement(query, params, "node", q.question_id)

    @staticmethod
    def _contains_edge(chapter_id: str, topic_id: str) -> CypherStatement:
        return CypherStatement(
            query=(
                "MATCH (c:Chapter {chapter_id: $chapter_id})\n"
                "MATCH (t:Topic {topic_id: $topic_id})\n"
                "MERGE (c)-[r:CONTAINS]->(t)\n"
                "SET r.updated_at = datetime()"
            ),
            params={"chapter_id": chapter_id, "topic_id": topic_id},
            category="edge",
            uid=f"contains:{chapter_id}->{topic_id}",
        )

    @staticmethod
    def _next_edge(from_id: str, to_id: str) -> CypherStatement:
        return CypherStatement(
            query=(
                "MATCH (a:Topic {topic_id: $from_id})\n"
                "MATCH (b:Topic {topic_id: $to_id})\n"
                "MERGE (a)-[r:NEXT]->(b)\n"
                "SET r.updated_at = datetime()"
            ),
            params={"from_id": from_id, "to_id": to_id},
            category="edge",
            uid=f"next:{from_id}->{to_id}",
        )

    @staticmethod
    def _prereq_edge(from_id: str, to_id: str) -> CypherStatement:
        return CypherStatement(
            query=(
                "MATCH (a:Topic {topic_id: $from_id})\n"
                "MATCH (b:Topic {topic_id: $to_id})\n"
                "MERGE (a)-[r:PREREQ]->(b)\n"
                "SET r.updated_at = datetime()"
            ),
            params={"from_id": from_id, "to_id": to_id},
            category="edge",
            uid=f"prereq:{from_id}->{to_id}",
        )

    @staticmethod
    def _has_diagram_edge(topic_id: str, diagram_id: str) -> CypherStatement:
        return CypherStatement(
            query=(
                "MATCH (t:Topic {topic_id: $topic_id})\n"
                "MATCH (d:Diagram {diagram_id: $diagram_id})\n"
                "MERGE (t)-[r:HAS_DIAGRAM]->(d)\n"
                "SET r.updated_at = datetime()"
            ),
            params={"topic_id": topic_id, "diagram_id": diagram_id},
            category="edge",
            uid=f"has_diagram:{topic_id}->{diagram_id}",
        )

    @staticmethod
    def _has_question_edge(topic_id: str, question_id: str) -> CypherStatement:
        return CypherStatement(
            query=(
                "MATCH (t:Topic {topic_id: $topic_id})\n"
                "MATCH (q:Question {question_id: $question_id})\n"
                "MERGE (t)-[r:HAS_QUESTION]->(q)\n"
                "SET r.updated_at = datetime()"
            ),
            params={"topic_id": topic_id, "question_id": question_id},
            category="edge",
            uid=f"has_question:{topic_id}->{question_id}",
        )
