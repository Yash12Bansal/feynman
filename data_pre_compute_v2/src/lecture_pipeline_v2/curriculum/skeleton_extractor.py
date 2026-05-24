"""BookSkeleton extraction — one LLM call to map the whole book's structure.

Carried from v1 with the v2 BookSkeleton model (no Units, no cross-chapter
prereqs at skeleton time — those live on Topic.prereq_topic_ids later).
"""

from __future__ import annotations

import json
import logging

from ..llm.base import LLMProvider
from ..pdf.parser import PDFContent
from ..pdf.toc import Chapter
from .models import BookSkeleton
from .prompts import build_skeleton_user_prompt, get_skeleton_system_prompt

logger = logging.getLogger(__name__)


class SkeletonExtractionError(Exception):
    def __init__(self, message: str, raw_response: str | None = None):
        super().__init__(message)
        self.raw_response = raw_response


class SkeletonExtractor:
    MAX_PREVIEW_CHARS = 1500
    MIN_PREVIEW_CHARS = 200
    MAX_RETRIES = 1

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    def extract(
        self,
        pdf_content: PDFContent,
        chapters: list[Chapter],
        subject_hint: str | None = None,
    ) -> BookSkeleton:
        if not chapters:
            raise SkeletonExtractionError("No chapters detected in PDF")

        toc_text = self._build_toc_text(chapters)
        previews = self._extract_chapter_previews(pdf_content, chapters)

        system_prompt = get_skeleton_system_prompt()
        user_prompt = build_skeleton_user_prompt(toc_text, previews, subject_hint)

        logger.info(
            "Extracting book skeleton: %d chapters, ~%d chars input",
            len(chapters), len(system_prompt) + len(user_prompt),
        )

        raw_json = self._call_llm(system_prompt, user_prompt)
        skeleton = self._parse_response(raw_json, pdf_content.total_pages)
        for w in self._validate_skeleton(skeleton, chapters):
            logger.warning("Skeleton validation: %s", w)
        return skeleton

    def _build_toc_text(self, chapters: list[Chapter]) -> str:
        lines = []
        for i, ch in enumerate(chapters, 1):
            lines.append(f"{i}. {ch.title} (pages {ch.start_page}-{ch.end_page})")
            for child in ch.children:
                lines.append(f"   - {child.title} (pages {child.start_page}-{child.end_page})")
        return "\n".join(lines)

    def _extract_chapter_previews(
        self, pdf_content: PDFContent, chapters: list[Chapter]
    ) -> list[dict]:
        max_chars = self.MAX_PREVIEW_CHARS
        if len(chapters) > 50:
            max_chars = 1000

        previews = []
        for i, ch in enumerate(chapters, 1):
            preview_text = self._extract_preview(pdf_content, ch, max_chars)
            previews.append({
                "chapter_index": i,
                "title": ch.title,
                "page_start": ch.start_page,
                "page_end": ch.end_page,
                "preview_text": preview_text,
            })
        return previews

    def _extract_preview(
        self, pdf_content: PDFContent, chapter: Chapter, max_chars: int
    ) -> str:
        text = pdf_content.get_text_for_range(chapter.start_page, chapter.start_page)
        pages_pulled = 1
        while len(text.strip()) < self.MIN_PREVIEW_CHARS and pages_pulled < 3:
            next_page = chapter.start_page + pages_pulled
            if next_page > chapter.end_page:
                break
            text = pdf_content.get_text_for_range(chapter.start_page, next_page)
            pages_pulled += 1
        return text.strip()[:max_chars]

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        last_error = None
        raw = None
        for attempt in range(self.MAX_RETRIES + 1):
            response = self.llm.generate_json(system_prompt, user_prompt)
            raw = response.content
            if response.usage:
                logger.info(
                    "Skeleton LLM call (attempt %d): in=%s out=%s",
                    attempt + 1,
                    response.usage.get("input_tokens", "?"),
                    response.usage.get("output_tokens", "?"),
                )
            try:
                json.loads(raw)
                return raw
            except json.JSONDecodeError as e:
                last_error = e
                logger.warning("Skeleton JSON parse failed (attempt %d): %s", attempt + 1, e)

        raise SkeletonExtractionError(
            f"LLM returned invalid JSON after {self.MAX_RETRIES + 1} attempts: {last_error}",
            raw_response=raw,
        )

    def _parse_response(self, raw_json: str, total_pages: int) -> BookSkeleton:
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            raise SkeletonExtractionError(f"Invalid JSON: {e}", raw_response=raw_json) from e

        if not data.get("total_pages"):
            data["total_pages"] = total_pages
        if "chapters" in data:
            data["total_chapters"] = len(data["chapters"])
        for ch in data.get("chapters", []):
            ch.setdefault("key_concepts", [])
            ch.setdefault("prerequisites_from", [])
            ch.setdefault("leads_to", [])

        try:
            return BookSkeleton.model_validate(data)
        except Exception as e:
            raise SkeletonExtractionError(
                f"Failed to parse BookSkeleton: {e}", raw_response=raw_json
            ) from e

    def _validate_skeleton(
        self, skeleton: BookSkeleton, chapters: list[Chapter]
    ) -> list[str]:
        warnings: list[str] = []
        toc_titles = {ch.title.lower().strip() for ch in chapters}
        skeleton_titles = {ch.title.lower().strip() for ch in skeleton.chapters}
        if missing := toc_titles - skeleton_titles:
            warnings.append(f"Chapters from TOC missing in skeleton: {missing}")
        if extra := skeleton_titles - toc_titles:
            warnings.append(f"Extra chapters in skeleton not in TOC: {extra}")
        all_titles = {ch.title for ch in skeleton.chapters}
        for ch in skeleton.chapters:
            for prereq in ch.prerequisites_from:
                if prereq not in all_titles:
                    warnings.append(f"Chapter '{ch.title}' references unknown prereq '{prereq}'")
                if prereq == ch.title:
                    warnings.append(f"Chapter '{ch.title}' lists itself as prereq")
            if ch.page_start > ch.page_end:
                warnings.append(f"Chapter '{ch.title}' invalid page range")
        return warnings
