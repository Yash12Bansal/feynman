"""Deterministic anchor extraction from PDF text using regex.

This is the part that CAN'T miss anything because it doesn't rely on LLM judgment.
Extracts structural markers that become the completeness checklist for LLM output.

Usage:
    extractor = DeterministicAnchorExtractor()
    anchors = extractor.extract_for_chapter(pdf_content, chapter)
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

# ---------------------------------------------------------------------------
# Compiled regex patterns — module-level for performance
# ---------------------------------------------------------------------------

# Section numbers: checked most-specific first to avoid false 2-level matches.
# Requires: start of line, optional whitespace, number, then uppercase title (3-80 chars).
_SECTION_3_LEVEL = re.compile(
    r"(?m)^\s*(\d{1,3}\.\d{1,3}\.\d{1,3})\s+([A-Z][^\n]{3,80})"
)
_SECTION_2_LEVEL = re.compile(
    r"(?m)^\s*(\d{1,3}\.\d{1,3})\s+([A-Z][^\n]{3,80})"
)
_SECTION_LETTER_SUB = re.compile(
    r"(?m)^\s*(\d{1,3}\.\d{1,3}\s*[a-z])\s+([A-Z][^\n]{3,80})"
)

# Figure references: "Fig. 12.3", "Figure 5", "FIGURE 12.3a"
# No IGNORECASE — [a-z]? for subfigure letters must not match uppercase.
_FIGURE_REF = re.compile(
    r"(?:[Ff]ig\.\s*|[Ff]igure\s+|FIGURE\s+|FIG\.\s*)"
    r"(\d{1,3}(?:\.\d{1,3})*[a-z]?)"
)

# Example references: "Example 12.1", "Worked Example 3.2", "Sample Problem 5.3"
_EXAMPLE_REF = re.compile(
    r"(?:Worked\s+Example|Sample\s+Problem|Example|EXAMPLE)"
    r"\s+(\d{1,3}(?:\.\d{1,3})*)",
    re.IGNORECASE,
)

# Equation references: "Eq. (3.5)", "Equation 12", "Eq. 3.5"
_EQUATION_REF = re.compile(
    r"(?:Eq(?:uation)?\.?\s+)\(?\s*(\d{1,3}(?:\.\d{1,3})*)\s*\)?",
    re.IGNORECASE,
)

# Defined terms — multiple linguistic patterns, lower recall expected.
_DEFINED_TERM_PATTERNS = [
    # "X is defined as" / "X is called" / "X is known as"
    re.compile(
        r"(?:^|\.\s+)([A-Z][a-z]+(?:\s+[a-z]+){0,4})\s+is\s+(?:defined\s+as|called|known\s+as)",
        re.MULTILINE,
    ),
    # "We define X as" / "We call X the"
    re.compile(r"[Ww]e\s+(?:define|call)\s+(?:the\s+)?(.{3,60}?)\s+(?:as|the)\b"),
    # "Definition:" or "DEFINITION:" header
    re.compile(r"(?:Definition|DEFINITION)[:\s]+([A-Z][^\n]{3,60})"),
    # "The term X is" / "The quantity X is" / "The property X refers to"
    re.compile(
        r"[Tt]he\s+(?:term|quantity|concept|property)\s+(.{3,50}?)\s+(?:is|refers\s+to|means)\b"
    ),
]


class DeterministicAnchorExtractor:
    """Extract verifiable anchors from PDF text BEFORE LLM extraction.

    These become the completeness checklist the LLM output is validated against.
    Stateless — no configuration needed.
    """

    def extract_anchors(self, chapter_text: str, pages: list) -> ExtractionAnchors:
        """Extract all anchor types from raw chapter text.

        Args:
            chapter_text: Full text of the chapter (concatenated pages).
            pages: List of page objects (only len is used for page_count).

        Returns:
            ExtractionAnchors with all detected structural markers.
        """
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
        """Convenience: extract anchors from a PDFContent + Chapter pair.

        Wires get_text_for_range and get_pages_for_range into the text-based
        core method.
        """
        text = pdf_content.get_text_for_range(chapter.start_page, chapter.end_page)
        pages = pdf_content.get_pages_for_range(chapter.start_page, chapter.end_page)
        return self.extract_anchors(text, pages)

    # ------------------------------------------------------------------
    # Section numbers — THE most reliable anchor (extraction floor)
    # ------------------------------------------------------------------

    def _find_section_numbers(self, text: str) -> list[SectionAnchor]:
        """Find all numbered section headings.

        Patterns are checked most-specific first (3-level before 2-level).
        Position-based dedup prevents a 3-level match from also producing
        a spurious 2-level match at the same text position.
        """
        anchors: list[SectionAnchor] = []
        seen_positions: set[int] = set()
        seen_numbers: set[str] = set()

        # Pass 1: three-level sections (e.g. 12.1.1)
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

        # Pass 2: two-level sections (e.g. 12.1) — skip consumed positions
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

        # Pass 3: letter sub-sections (e.g. 12.1a) — skip consumed positions
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

        # Sort by numeric section number
        anchors.sort(key=self._section_sort_key)
        return anchors

    @staticmethod
    def _section_sort_key(anchor: SectionAnchor) -> tuple:
        """Sort key for section numbers: (12, 1, 1) for '12.1.1'."""
        parts = []
        for p in anchor.section_number.split("."):
            p = p.strip()
            # Handle letter suffixes like "12.1a" -> (12, 1, 'a')
            if p.isdigit():
                parts.append((0, int(p)))
            else:
                # Extract numeric prefix and letter suffix
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

    # ------------------------------------------------------------------
    # Figure references
    # ------------------------------------------------------------------

    def _find_figure_references(self, text: str) -> list[str]:
        """Find all figure references, normalized to 'Figure X.Y' form."""
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

    # ------------------------------------------------------------------
    # Example references
    # ------------------------------------------------------------------

    def _find_example_references(self, text: str) -> list[str]:
        """Find all example references, normalized to 'Example X.Y' form."""
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

    # ------------------------------------------------------------------
    # Equation references
    # ------------------------------------------------------------------

    def _find_equations(self, text: str) -> list[str]:
        """Find explicit equation references, normalized to 'Eq. (X.Y)' form."""
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

    # ------------------------------------------------------------------
    # Defined terms
    # ------------------------------------------------------------------

    def _find_defined_terms(self, text: str) -> list[str]:
        """Find terms introduced via definitional language patterns.

        Lower recall than other anchors — bold/italic formatting is lost
        in PDF text extraction. Accepts only explicit linguistic patterns.
        """
        seen_lower: set[str] = set()
        terms: list[str] = []

        for pattern in _DEFINED_TERM_PATTERNS:
            for m in pattern.finditer(text):
                term = m.group(1).strip()
                # Filter: too short or too long
                if len(term) < 3 or len(term) > 60:
                    continue
                # Case-insensitive dedup
                if term.lower() in seen_lower:
                    continue
                seen_lower.add(term.lower())
                terms.append(term)

        terms.sort(key=str.lower)
        return terms

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ref_sort_key(ref: str) -> tuple:
        """Sort 'Figure 12.3' or 'Eq. (12.4)' style references by numeric parts."""
        nums = re.findall(r"\d+", ref)
        return tuple(int(n) for n in nums)
