"""Table of Contents detection and chapter splitting."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .parser import PDFContent


@dataclass
class Chapter:
    """A chapter detected from the PDF's table of contents."""
    title: str
    level: int  # 1 = top-level chapter, 2 = section, etc.
    start_page: int
    end_page: int
    children: list[Chapter] = field(default_factory=list)

    @property
    def page_count(self) -> int:
        return self.end_page - self.start_page + 1

    def get_text(self, pdf_content: PDFContent) -> str:
        return pdf_content.get_text_for_range(self.start_page, self.end_page)

    def get_pages(self, pdf_content: PDFContent):
        return pdf_content.get_pages_for_range(self.start_page, self.end_page)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "level": self.level,
            "start_page": self.start_page,
            "end_page": self.end_page,
            "page_count": self.page_count,
            "children": [c.to_dict() for c in self.children],
        }


class TOCExtractor:
    """Extract and structure chapters from PDF table of contents."""

    def extract_chapters(self, pdf_content: PDFContent) -> list[Chapter]:
        """Build chapter tree from PDF TOC.

        If no TOC is found in PDF metadata, attempts heuristic detection
        from page text content.
        """
        if pdf_content.toc_raw:
            return self._from_toc_metadata(pdf_content)
        return self._from_heuristic(pdf_content)

    def _from_toc_metadata(self, pdf_content: PDFContent) -> list[Chapter]:
        """Build chapter tree from PyMuPDF's get_toc() output."""
        toc = pdf_content.toc_raw
        if not toc:
            return []

        # Assign end pages: each entry ends where the next same-or-higher-level entry starts
        entries = []
        for i, (level, title, start_page) in enumerate(toc):
            # Find end page: next entry at same or higher level, or last page
            end_page = pdf_content.total_pages
            for j in range(i + 1, len(toc)):
                next_level, _, next_start = toc[j]
                if next_level <= level:
                    end_page = next_start - 1
                    break
                # If next entry is deeper, keep looking for end
            # But also cap at next entry's start - 1 if it's deeper
            if i + 1 < len(toc):
                # End page is at most one page before the very next entry at same/higher level
                # But content may overlap with sub-sections, so use the broader range
                pass

            entries.append(Chapter(
                title=title.strip(),
                level=level,
                start_page=max(1, start_page),
                end_page=max(1, end_page),
            ))

        # Build tree: nest children under parents
        return self._build_tree(entries)

    def _build_tree(self, flat_entries: list[Chapter]) -> list[Chapter]:
        """Nest flat TOC entries into a tree based on levels."""
        if not flat_entries:
            return []

        root_chapters: list[Chapter] = []
        stack: list[Chapter] = []

        for entry in flat_entries:
            # Pop stack until we find a parent with lower level
            while stack and stack[-1].level >= entry.level:
                stack.pop()

            if stack:
                # This entry is a child of the top of stack
                parent = stack[-1]
                parent.children.append(entry)
                # Update parent's end page to encompass child
                parent.end_page = max(parent.end_page, entry.end_page)
            else:
                root_chapters.append(entry)

            stack.append(entry)

        return root_chapters

    def _from_heuristic(self, pdf_content: PDFContent) -> list[Chapter]:
        """Detect chapters heuristically when no TOC metadata exists.

        Looks for patterns like 'Chapter 1', 'CHAPTER I', 'Unit 1', numbered headings, etc.
        """
        chapter_pattern = re.compile(
            r'^(?:chapter|unit|module|lesson|part)\s+[\divxlc]+[.:)?\s]',
            re.IGNORECASE | re.MULTILINE,
        )

        chapters: list[Chapter] = []

        for page in pdf_content.pages:
            lines = page.text.split('\n')
            for line in lines[:10]:  # Check first 10 lines of each page
                line_stripped = line.strip()
                if chapter_pattern.match(line_stripped) and len(line_stripped) < 200:
                    chapters.append(Chapter(
                        title=line_stripped,
                        level=1,
                        start_page=page.page_number,
                        end_page=pdf_content.total_pages,
                    ))

        # Fix end pages: each chapter ends where the next begins
        for i in range(len(chapters) - 1):
            chapters[i].end_page = chapters[i + 1].start_page - 1

        return chapters
