"""Table of Contents detection and chapter splitting.

Ported from v1, then extended for v2 with a "chapter title normalizer" that
handles digitised books whose PDF bookmarks are internal filenames rather
than real chapter titles (e.g. H.C. Verma's 'COP1_05_1_Pg_064-071' style).

Normalizer behaviour:
  1. Detect bookmarks that look like internal filenames.
  2. Pull the actual chapter number out of the bookmark name.
  3. Group consecutive bookmarks with the same chapter number into one Chapter
     spanning all their pages (some books split chapters across 2-3 bookmarks).
  4. Read the first ~2 KB of the chapter's pages and search for a real heading
     ("CHAPTER N\\nTITLE_IN_CAPS"). Use that as the title; fall back to
     "Chapter N" if nothing is found.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from .parser import PDFContent

logger = logging.getLogger(__name__)


@dataclass
class Chapter:
    title: str
    level: int
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


# ---------------------------------------------------------------------------
# Chapter title normalizer — for PDFs whose bookmarks are internal filenames
# ---------------------------------------------------------------------------

_FILENAME_LIKE_BOOKMARK = re.compile(
    r"^[A-Za-z]+\d*_\d{1,3}(?:[_\-]\d{1,3})?_(?:Pg|pg|PG)[_\-]\d",
)

_CHAPTER_NUMBER_FROM_BOOKMARK = re.compile(
    r"[_\-](\d{1,3})[_\-]\d{1,3}[_\-](?:Pg|pg|PG)",
)

# Title characters: caps, digits, common punctuation, NO newlines so matches stop at line ends.
_TITLE_LINE = r"[A-Z][A-Z0-9’'’,.:&\-/ ]{2,80}"

# Match "CHAPTER 5\nNEWTON'S LAWS OF MOTION[\nOPTIONAL CONTINUATION][\nOPTIONAL CONT 2]\n..."
# Continuations are bona-fide additional title lines (all-caps, not starting with a digit),
# so section headers like "5.1 INTRODUCTION" and body lines starting with "Newton's" are excluded.
_CHAPTER_HEADING_IN_TEXT = re.compile(
    r"(?:^|\n)[ \t]*(?:CHAPTER|Chapter)[ \t]+(\d{1,3})[ \t]*\n+[ \t]*"
    rf"({_TITLE_LINE}(?:\n[ \t]*{_TITLE_LINE}){{0,2}})"
    r"(?=\s*\n)"
)

# Bare-number style: "5\nTITLE\n..." (some books skip the literal "CHAPTER" word).
_BARE_NUMBER_HEADING = re.compile(
    r"(?:^|\n)[ \t]*(\d{1,3})[ \t]*\n+[ \t]*"
    rf"({_TITLE_LINE}(?:\n[ \t]*{_TITLE_LINE}){{0,2}})"
    r"(?=\s*\n)",
    re.MULTILINE,
)


def _looks_like_filename(title: str) -> bool:
    return bool(_FILENAME_LIKE_BOOKMARK.match(title.strip()))


def _chapter_number_from_bookmark(title: str) -> int | None:
    m = _CHAPTER_NUMBER_FROM_BOOKMARK.search(title)
    return int(m.group(1)) if m else None


def _normalise_caps_title(raw: str) -> str:
    """'NEWTON'S LAWS OF MOTION\\nON A STRING' -> 'Newton's Laws of Motion on a String'.

    Collapses any newlines (multi-line titles) and intra-line whitespace runs,
    then title-cases each word with short connector words lowercased.
    """
    flat = re.sub(r"\s+", " ", raw.strip())
    small = {"of", "the", "in", "a", "an", "and", "or", "for", "to", "on", "by"}
    words = flat.split()
    out = []
    for i, w in enumerate(words):
        lw = w.lower()
        if i != 0 and lw in small:
            out.append(lw)
        else:
            out.append(lw[:1].upper() + lw[1:])
    return " ".join(out)


def _detect_title_from_pages(text: str, expected_chapter_num: int | None) -> str | None:
    """Best-effort extraction of a real chapter title from page text."""
    head = text[:3000]

    for match in _CHAPTER_HEADING_IN_TEXT.finditer(head):
        found_num = int(match.group(1))
        if expected_chapter_num is None or found_num == expected_chapter_num:
            return _normalise_caps_title(match.group(2))

    if expected_chapter_num is not None:
        for match in _BARE_NUMBER_HEADING.finditer(head):
            if int(match.group(1)) == expected_chapter_num:
                return _normalise_caps_title(match.group(2))

    return None


def normalize_chapter_titles(
    chapters: list[Chapter],
    pdf_content: PDFContent,
) -> list[Chapter]:
    """Group filename-style bookmarks by chapter number and recover real titles.

    Returns a new list (does not mutate input). If no bookmarks look like
    filenames, returns the input unchanged.
    """
    if not chapters or not any(_looks_like_filename(c.title) for c in chapters):
        return chapters

    grouped: dict[int, list[Chapter]] = {}
    unkeyed: list[Chapter] = []
    for ch in chapters:
        num = _chapter_number_from_bookmark(ch.title) if _looks_like_filename(ch.title) else None
        if num is None:
            unkeyed.append(ch)
        else:
            grouped.setdefault(num, []).append(ch)

    out: list[Chapter] = []
    for num in sorted(grouped.keys()):
        parts = sorted(grouped[num], key=lambda c: c.start_page)
        start_page = parts[0].start_page
        end_page = max(p.end_page for p in parts)
        page_text = pdf_content.get_text_for_range(start_page, min(start_page + 2, end_page))

        detected = _detect_title_from_pages(page_text, num)
        title = detected or f"Chapter {num}"
        if detected is None:
            logger.warning(
                "Could not detect real title for chapter %d (bookmarks: %s); "
                "using '%s'", num, [p.title for p in parts], title,
            )

        children: list[Chapter] = []
        for p in parts:
            children.extend(p.children)

        out.append(Chapter(
            title=title,
            level=parts[0].level,
            start_page=start_page,
            end_page=end_page,
            children=children,
        ))

    out.extend(unkeyed)
    out.sort(key=lambda c: c.start_page)
    return out


class TOCExtractor:
    def extract_chapters(self, pdf_content: PDFContent) -> list[Chapter]:
        if pdf_content.toc_raw:
            chapters = self._from_toc_metadata(pdf_content)
        else:
            chapters = self._from_heuristic(pdf_content)
        return normalize_chapter_titles(chapters, pdf_content)

    def _from_toc_metadata(self, pdf_content: PDFContent) -> list[Chapter]:
        toc = pdf_content.toc_raw
        if not toc:
            return []

        entries = []
        for i, (level, title, start_page) in enumerate(toc):
            end_page = pdf_content.total_pages
            for j in range(i + 1, len(toc)):
                next_level, _, next_start = toc[j]
                if next_level <= level:
                    end_page = next_start - 1
                    break

            entries.append(Chapter(
                title=title.strip(),
                level=level,
                start_page=max(1, start_page),
                end_page=max(1, end_page),
            ))

        return self._build_tree(entries)

    def _build_tree(self, flat_entries: list[Chapter]) -> list[Chapter]:
        if not flat_entries:
            return []

        root_chapters: list[Chapter] = []
        stack: list[Chapter] = []

        for entry in flat_entries:
            while stack and stack[-1].level >= entry.level:
                stack.pop()

            if stack:
                parent = stack[-1]
                parent.children.append(entry)
                parent.end_page = max(parent.end_page, entry.end_page)
            else:
                root_chapters.append(entry)

            stack.append(entry)

        return root_chapters

    def _from_heuristic(self, pdf_content: PDFContent) -> list[Chapter]:
        chapter_pattern = re.compile(
            r'^(?:chapter|unit|module|lesson|part)\s+[\divxlc]+[.:)?\s]',
            re.IGNORECASE | re.MULTILINE,
        )

        chapters: list[Chapter] = []

        for page in pdf_content.pages:
            lines = page.text.split('\n')
            for line in lines[:10]:
                line_stripped = line.strip()
                if chapter_pattern.match(line_stripped) and len(line_stripped) < 200:
                    chapters.append(Chapter(
                        title=line_stripped,
                        level=1,
                        start_page=page.page_number,
                        end_page=pdf_content.total_pages,
                    ))

        for i in range(len(chapters) - 1):
            chapters[i].end_page = chapters[i + 1].start_page - 1

        return chapters
