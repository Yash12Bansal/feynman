"""ChapterLecturePlanner — produces a ChapterLecturePlan per chapter.

Sync (uses v2's AnthropicProvider.generate_json), matching the existing
TopicExtractor / ScriptWriter call style. Async-bridging is handled at the
pipeline layer when concurrent chapter planning is wanted.
"""

from __future__ import annotations

import json

import structlog

from lecture_pipeline_v2.curriculum.lecture_plan.models import ChapterLecturePlan
from lecture_pipeline_v2.curriculum.lecture_plan.prompts import (
    CHAPTER_PLANNING_SYSTEM_PROMPT,
)
from lecture_pipeline_v2.curriculum.models import Chapter, Topic
from lecture_pipeline_v2.llm.base import LLMProvider

logger = structlog.get_logger()


class ChapterLecturePlanner:
    """Plans a chapter-level arc per chapter via v2's sync AnthropicProvider."""

    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    def plan_for_all(
        self,
        chapters: list[Chapter],
        topics_by_chapter: dict[str, list[Topic]],
    ) -> dict[str, ChapterLecturePlan]:
        result: dict[str, ChapterLecturePlan] = {}
        for chapter in chapters:
            topics = topics_by_chapter.get(chapter.chapter_id, [])
            if not topics:
                logger.warning(
                    "chapter_planner.no_topics",
                    chapter_id=chapter.chapter_id,
                )
                continue
            plan = self._plan_one(chapter, topics)
            if plan is not None:
                result[chapter.chapter_id] = plan
        return result

    def _plan_one(
        self,
        chapter: Chapter,
        topics: list[Topic],
    ) -> ChapterLecturePlan | None:
        user_prompt = self._build_user_prompt(chapter, topics)
        try:
            response = self.llm.generate_json(
                CHAPTER_PLANNING_SYSTEM_PROMPT, user_prompt
            )
        except Exception as exc:
            logger.error(
                "chapter_planner.llm_call_failed",
                chapter_id=chapter.chapter_id,
                error=str(exc),
            )
            return None

        try:
            data = json.loads(response.content)
        except json.JSONDecodeError as exc:
            logger.error(
                "chapter_planner.json_decode_failed",
                chapter_id=chapter.chapter_id,
                error=str(exc),
                content_preview=response.content[:200],
            )
            return None

        # Belt-and-suspenders: the LLM occasionally returns topic_ids that
        # don't exist. Filter out invalid entries before validation.
        valid_topic_ids = {t.topic_id for t in topics}
        if "concept_sequence" in data:
            seq = data["concept_sequence"]
            filtered = [tid for tid in seq if tid in valid_topic_ids]
            if len(filtered) < len(seq):
                logger.warning(
                    "chapter_planner.filtered_invalid_topic_ids",
                    chapter_id=chapter.chapter_id,
                    dropped=len(seq) - len(filtered),
                )
            data["concept_sequence"] = filtered

        try:
            return ChapterLecturePlan.model_validate(data)
        except Exception as exc:
            logger.error(
                "chapter_planner.validation_failed",
                chapter_id=chapter.chapter_id,
                error=str(exc),
            )
            return None

    def _build_user_prompt(self, chapter: Chapter, topics: list[Topic]) -> str:
        lines: list[str] = [
            f"# Chapter: {chapter.title}",
            f"chapter_id: {chapter.chapter_id}",
            "",
            "## Chapter summary (from the textbook):",
            chapter.summary or "(no summary available)",
            "",
            "## Topics in this chapter (book order):",
        ]
        for i, topic in enumerate(topics):
            lines.append(
                f"### {i + 1}. {topic.topic_name}  "
                f"(topic_id: {topic.topic_id}, section: {topic.section_number})"
            )
            understanding = (topic.our_understanding or "").strip()
            if len(understanding) > 400:
                understanding = understanding[:400] + "…"
            lines.append(f"Our understanding: {understanding}")
            if topic.examples:
                lines.append(f"Has {len(topic.examples)} example(s)")
            if topic.has_diagram_ids:
                lines.append(f"Has {len(topic.has_diagram_ids)} diagram(s)")
            lines.append("")

        lines.append(
            "Produce a ChapterLecturePlan JSON for this chapter. "
            "All entries in concept_sequence must be from the topic_ids listed above."
        )
        return "\n".join(lines)
