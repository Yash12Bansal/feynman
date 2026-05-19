"""Deterministic anchor extraction from PDF text using regex.

Ported from v1 verbatim; logic unchanged. Section anchors drive v2's
topic boundary detection — every numbered section becomes one Topic.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from .models import ExtractionAnchors, SectionAnchor

if TYPE_CHECKING:
    from ...pdf.parser import PDFContent
    from ...pdf.toc import Chapter

logger = logging.getLogger(__name__)

_SECTION_3_LEVEL = re.compile(
    r"(?m)^\s*(\d{1,3}\.\d{1,3}\.\d{1,3})\s+([A-Z][^\n]{3,80})"
)
_SECTION_2_LEVEL = re.compile(
    r"(?m)^\s*(\d{1,3}\.\d{1,3})\s+([A-Z][^\n]{3,80})"
)
_SECTION_LETTER_SUB = re.compile(
    r"(?m)^\s*(\d{1,3}\.\d{1,3}\s*[a-z])\s+([A-Z][^\n]{3,80})"
)

_FIGURE_REF = re.compile(
    r"(?:[Ff]ig\.\s*|[Ff]igure\s+|FIGURE\s+|FIG\.\s*)"
    r"(\d{1,3}(?:\.\d{1,3})*[a-z]?)"
)

_EXAMPLE_REF = re.compile(
    r"(?:Worked\s+Example|Sample\s+Problem|Example|EXAMPLE)"
    r"\s+(\d{1,3}(?:\.\d{1,3})*)",
    re.IGNORECASE,
)

_EQUATION_REF = re.compile(
    r"(?:Eq(?:uation)?\.?\s+)\(?\s*(\d{1,3}(?:\.\d{1,3})*)\s*\)?",
    re.IGNORECASE,
)

_DEFINED_TERM_PATTERNS = [
    re.compile(
        r"(?:^|\.\s+)([A-Z][a-z]+(?:\s+[a-z]+){0,4})\s+is\s+(?:defined\s+as|called|known\s+as)",
        re.MULTILINE,
    ),
    re.compile(r"[Ww]e\s+(?:define|call)\s+(?:the\s+)?(.{3,60}?)\s+(?:as|the)\b"),
    re.compile(r"(?:Definition|DEFINITION)[:\s]+([A-Z][^\n]{3,60})"),
    re.compile(
        r"[Tt]he\s+(?:term|quantity|concept|property)\s+(.{3,50}?)\s+(?:is|refers\s+to|means)\b"
    ),
]


class DeterministicAnchorExtractor:
    """Extract structural anchors from raw text via regex."""

    def extract_anchors(self, chapter_text: str, pages: list) -> ExtractionAnchors:
        if not chapter_text.strip():
            logger.warning("Empty chapter text, returning empty anchors")
            return ExtractionAnchors(page_count=len(pages))

        sections = self._find_section_numbers(chapter_text)
        equations = self._find_equations(chapter_text)
        figures = self._find_figure_references(chapter_text)
        examples = self._find_example_references(chapter_text)
        terms = self._find_defined_terms(chapter_text)

        anchors = ExtractionAnchors(
            section_numbers=sections,
            equations=equations,
            figure_refs=figures,
            example_refs=examples,
            defined_terms=terms,
            page_count=len(pages),
        )

        logger.info(anchors.summary())
        return anchors

    def extract_for_chapter(
        self, pdf_content: PDFContent, chapter: Chapter
    ) -> ExtractionAnchors:
        text = pdf_content.get_text_for_range(chapter.start_page, chapter.end_page)
        pages = pdf_content.get_pages_for_range(chapter.start_page, chapter.end_page)
        return self.extract_anchors(text, pages)

    def _find_section_numbers(self, text: str) -> list[SectionAnchor]:
        anchors: list[SectionAnchor] = []
        seen_positions: set[int] = set()
        seen_numbers: set[str] = set()

        for m in _SECTION_3_LEVEL.finditer(text):
            num = m.group(1)
            title = m.group(2).strip()[:80]
            if num not in seen_numbers:
                seen_numbers.add(num)
                seen_positions.add(m.start())
                anchors.append(SectionAnchor(
                    section_number=num,
                    title=title,
                    depth=num.count(".") + 1,
                ))

        for m in _SECTION_2_LEVEL.finditer(text):
            if m.start() in seen_positions:
                continue
            num = m.group(1)
            title = m.group(2).strip()[:80]
            if num not in seen_numbers:
                seen_numbers.add(num)
                seen_positions.add(m.start())
                anchors.append(SectionAnchor(
                    section_number=num,
                    title=title,
                    depth=num.count(".") + 1,
                ))

        for m in _SECTION_LETTER_SUB.finditer(text):
            if m.start() in seen_positions:
                continue
            num = m.group(1).strip()
            title = m.group(2).strip()[:80]
            if num not in seen_numbers:
                seen_numbers.add(num)
                anchors.append(SectionAnchor(
                    section_number=num,
                    title=title,
                    depth=num.count(".") + 1,
                ))

        anchors.sort(key=self._section_sort_key)
        return anchors

    @staticmethod
    def _section_sort_key(anchor: SectionAnchor) -> tuple:
        parts = []
        for p in anchor.section_number.split("."):
            p = p.strip()
            if p.isdigit():
                parts.append((0, int(p)))
            else:
                digits = ""
                rest = p
                for c in p:
                    if c.isdigit():
                        digits += c
                    else:
                        rest = p[len(digits):]
                        break
                if digits:
                    parts.append((0, int(digits)))
                if rest:
                    parts.append((1, ord(rest[0])))
        return tuple(parts)

    def _find_figure_references(self, text: str) -> list[str]:
        seen: set[str] = set()
        refs: list[str] = []
        for m in _FIGURE_REF.finditer(text):
            num = m.group(1).strip()
            canonical = f"Figure {num}"
            if canonical not in seen:
                seen.add(canonical)
                refs.append(canonical)
        refs.sort(key=self._ref_sort_key)
        return refs

    def _find_example_references(self, text: str) -> list[str]:
        seen: set[str] = set()
        refs: list[str] = []
        for m in _EXAMPLE_REF.finditer(text):
            num = m.group(1).strip()
            canonical = f"Example {num}"
            if canonical not in seen:
                seen.add(canonical)
                refs.append(canonical)
        refs.sort(key=self._ref_sort_key)
        return refs

    def _find_equations(self, text: str) -> list[str]:
        seen: set[str] = set()
        refs: list[str] = []
        for m in _EQUATION_REF.finditer(text):
            num = m.group(1).strip()
            canonical = f"Eq. ({num})"
            if canonical not in seen:
                seen.add(canonical)
                refs.append(canonical)
        refs.sort(key=self._ref_sort_key)
        return refs

    def _find_defined_terms(self, text: str) -> list[str]:
        seen_lower: set[str] = set()
        terms: list[str] = []

        for pattern in _DEFINED_TERM_PATTERNS:
            for m in pattern.finditer(text):
                term = m.group(1).strip()
                if len(term) < 3 or len(term) > 60:
                    continue
                if term.lower() in seen_lower:
                    continue
                seen_lower.add(term.lower())
                terms.append(term)

        terms.sort(key=str.lower)
        return terms

    @staticmethod
    def _ref_sort_key(ref: str) -> tuple:
        nums = re.findall(r"\d+", ref)
        return tuple(int(n) for n in nums)
