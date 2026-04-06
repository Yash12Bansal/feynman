"""Book skeleton extraction — single LLM call to extract a textbook's global structure.

Usage:
    extractor = SkeletonExtractor(llm_provider)
    skeleton = extractor.extract(pdf_content, chapters)
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
    """Raised when skeleton extraction fails after retries."""

    def __init__(self, message: str, raw_response: str | None = None):
        super().__init__(message)
        self.raw_response = raw_response


class SkeletonExtractor:
    """Extracts a BookSkeleton from a parsed PDF via a single LLM call."""

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
        """Extract book skeleton from PDF content and detected chapters.

        Args:
            pdf_content: Parsed PDF with all pages.
            chapters: Top-level chapters from TOCExtractor.
            subject_hint: Optional subject override (e.g. "physics").

        Returns:
            BookSkeleton with chapter summaries, units, and prerequisites.

        Raises:
            SkeletonExtractionError: If extraction fails after retries.
        """
        if not chapters:
            raise SkeletonExtractionError("No chapters detected in PDF")

        toc_text = self._build_toc_text(chapters)
        previews = self._extract_chapter_previews(pdf_content, chapters)

        system_prompt = get_skeleton_system_prompt()
        user_prompt = build_skeleton_user_prompt(toc_text, previews, subject_hint)

        logger.info(
            "Extracting book skeleton: %d chapters, ~%d chars input",
            len(chapters),
            len(system_prompt) + len(user_prompt),
        )

        raw_json = self._call_llm(system_prompt, user_prompt)
        skeleton = self._parse_response(raw_json, pdf_content.total_pages)
        warnings = self._validate_skeleton(skeleton, chapters)
        for w in warnings:
            logger.warning("Skeleton validation: %s", w)

        return skeleton

    def _build_toc_text(self, chapters: list[Chapter]) -> str:
        """Format chapter list as a numbered TOC string."""
        lines = []
        for i, ch in enumerate(chapters, 1):
            lines.append(f"{i}. {ch.title} (pages {ch.start_page}-{ch.end_page})")
            for child in ch.children:
                lines.append(f"   - {child.title} (pages {child.start_page}-{child.end_page})")
        return "\n".join(lines)

    def _extract_chapter_previews(
        self,
        pdf_content: PDFContent,
        chapters: list[Chapter],
    ) -> list[dict[str, str]]:
        """Extract first 2-3 paragraphs from each chapter."""
        max_chars = self.MAX_PREVIEW_CHARS
        if len(chapters) > 50:
            max_chars = 1000
            logger.info("Large book (%d chapters), reducing preview to %d chars", len(chapters), max_chars)

        previews = []
        for i, ch in enumerate(chapters, 1):
            preview_text = self._extract_preview_for_chapter(pdf_content, ch, max_chars)
            previews.append({
                "chapter_index": i,
                "title": ch.title,
                "page_start": ch.start_page,
                "page_end": ch.end_page,
                "preview_text": preview_text,
            })
        return previews

    def _extract_preview_for_chapter(
        self,
        pdf_content: PDFContent,
        chapter: Chapter,
        max_chars: int | None = None,
    ) -> str:
        """Get the first ~1500 chars of a chapter's text.

        If the first page has less than MIN_PREVIEW_CHARS, extends to subsequent pages.
        """
        if max_chars is None:
            max_chars = self.MAX_PREVIEW_CHARS

        text = pdf_content.get_text_for_range(chapter.start_page, chapter.start_page)

        # If first page is sparse (title page, image-only), pull more pages
        pages_pulled = 1
        while len(text.strip()) < self.MIN_PREVIEW_CHARS and pages_pulled < 3:
            next_page = chapter.start_page + pages_pulled
            if next_page > chapter.end_page:
                break
            text = pdf_content.get_text_for_range(chapter.start_page, next_page)
            pages_pulled += 1

        return text.strip()[:max_chars]

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Call LLM and return raw JSON string. Retries once on parse failure."""
        last_error = None
        raw = None

        for attempt in range(self.MAX_RETRIES + 1):
            response = self.llm.generate_json(system_prompt, user_prompt)
            raw = response.content

            if response.usage:
                logger.info(
                    "LLM call (attempt %d): %s tokens in, %s tokens out",
                    attempt + 1,
                    response.usage.get("input_tokens", "?"),
                    response.usage.get("output_tokens", "?"),
                )

            try:
                json.loads(raw)
                return raw
            except json.JSONDecodeError as e:
                last_error = e
                logger.warning(
                    "JSON parse failed (attempt %d/%d): %s",
                    attempt + 1,
                    self.MAX_RETRIES + 1,
                    str(e),
                )

        raise SkeletonExtractionError(
            f"LLM returned invalid JSON after {self.MAX_RETRIES + 1} attempts: {last_error}",
            raw_response=raw,
        )

    def _parse_response(self, raw_json: str, total_pages: int) -> BookSkeleton:
        """Parse LLM JSON into BookSkeleton with validation and fixups."""
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            raise SkeletonExtractionError(
                f"Invalid JSON in LLM response: {e}",
                raw_response=raw_json,
            ) from e

        # Fix total_pages if missing or zero
        if not data.get("total_pages"):
            data["total_pages"] = total_pages

        # Fix total_chapters to match actual chapter count
        if "chapters" in data:
            data["total_chapters"] = len(data["chapters"])

        # Ensure optional list fields have defaults
        for ch in data.get("chapters", []):
            ch.setdefault("key_concepts", [])
            ch.setdefault("prerequisites_from", [])
            ch.setdefault("leads_to", [])
        data.setdefault("units", [])
        data.setdefault("cross_chapter_prerequisites", [])

        try:
            return BookSkeleton.model_validate(data)
        except Exception as e:
            raise SkeletonExtractionError(
                f"Failed to parse BookSkeleton: {e}",
                raw_response=raw_json,
            ) from e

    def _validate_skeleton(
        self, skeleton: BookSkeleton, chapters: list[Chapter]
    ) -> list[str]:
        """Post-parse validation. Returns list of warnings."""
        warnings: list[str] = []

        # Check all TOC chapters are represented
        toc_titles = {ch.title.lower().strip() for ch in chapters}
        skeleton_titles = {ch.title.lower().strip() for ch in skeleton.chapters}

        missing = toc_titles - skeleton_titles
        if missing:
            warnings.append(f"Chapters from TOC missing in skeleton: {missing}")

        extra = skeleton_titles - toc_titles
        if extra:
            warnings.append(f"Extra chapters in skeleton not in TOC: {extra}")

        # Check for circular prerequisites
        all_titles = {ch.title for ch in skeleton.chapters}
        for ch in skeleton.chapters:
            for prereq in ch.prerequisites_from:
                if prereq not in all_titles:
                    warnings.append(
                        f"Chapter '{ch.title}' references unknown prerequisite '{prereq}'"
                    )
                if prereq == ch.title:
                    warnings.append(f"Chapter '{ch.title}' lists itself as prerequisite")

        # Check page ranges
        for ch in skeleton.chapters:
            if ch.page_start > ch.page_end:
                warnings.append(
                    f"Chapter '{ch.title}' has invalid page range: "
                    f"{ch.page_start}-{ch.page_end}"
                )

        # Check subject is non-empty
        if not skeleton.subject.strip():
            warnings.append("Subject field is empty")

        return warnings
