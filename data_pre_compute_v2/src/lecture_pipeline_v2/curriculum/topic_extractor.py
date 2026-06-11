"""Per-section Topic extraction — one anchored section becomes one Topic.

The chapter text is sliced by section anchors (from anchors module).
For each section we make ONE LLM call that jointly produces:
  - our_understanding (teacher-voice explanation)
  - examples (concrete illustrations)

Topic identity, ordering, and orig_book_content are computed deterministically
from anchors + chapter text — no LLM involvement, so they survive re-runs.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from ..llm.base import LLMProvider
from .anchors.models import ExtractionAnchors, SectionAnchor
from .id_generator import generate_chapter_uid, generate_topic_uid
from .models import BookExample, BookSkeleton, Topic
from .prompts import build_topic_user_prompt, get_topic_system_prompt

logger = logging.getLogger(__name__)


def _parse_book_examples(raw: object) -> list[BookExample]:
    """Coerce the LLM's `book_examples` array into typed BookExample rows.

    Defensive: drop malformed entries (with a warning) rather than failing the
    whole topic. A missing `verbatim_text` or unknown `kind` makes an entry
    unusable — keep the rest. Bias toward salvage; coverage validator will
    surface real gaps later.
    """
    if not isinstance(raw, list):
        return []
    out: list[BookExample] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            logger.debug("book_examples[%d] not a dict, skipping", i)
            continue
        verbatim = str(entry.get("verbatim_text") or "").strip()
        kind = entry.get("kind")
        lesson_focus = str(entry.get("lesson_focus") or "").strip()
        if not verbatim or kind not in ("worked_out", "inline") or not lesson_focus:
            logger.warning(
                "book_examples[%d] missing required fields "
                "(verbatim_text/kind/lesson_focus); skipping",
                i,
            )
            continue
        setup_facts_raw = entry.get("setup_facts") or []
        setup_facts = (
            [str(f).strip() for f in setup_facts_raw if str(f).strip()]
            if isinstance(setup_facts_raw, list)
            else []
        )
        page_number = entry.get("page_number")
        out.append(
            BookExample(
                verbatim_text=verbatim,
                page_number=int(page_number) if isinstance(page_number, int) else None,
                kind=kind,
                lesson_focus=lesson_focus,
                setup_facts=setup_facts,
                has_derivation=bool(entry.get("has_derivation", False)),
            )
        )
    return out


@dataclass
class TopicExtractionReport:
    sections_seen: int = 0
    topics_extracted: int = 0
    topics_skipped_existing: int = 0
    topics_failed: int = 0
    elapsed_seconds: float = 0.0
    failures: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"Topic extraction — {self.topics_extracted}/{self.sections_seen} extracted, "
            f"{self.topics_skipped_existing} skipped (already in graph), "
            f"{self.topics_failed} failed, "
            f"{self.elapsed_seconds:.1f}s"
        )


class TopicExtractionError(Exception):
    def __init__(self, message: str, raw_response: str | None = None):
        super().__init__(message)
        self.raw_response = raw_response


def _build_section_pattern(section_number: str) -> re.Pattern:
    """Regex that matches the start of a section heading in chapter text.

    Matches '12.1', '12.1 Energy', '12.1.1', '12.1.1 Energy in SHM' at line start
    (with optional whitespace), case-insensitive on the title part.
    """
    escaped = re.escape(section_number)
    return re.compile(rf"(?m)^\s*{escaped}(?:\s|$)")


def slice_chapter_by_sections(
    chapter_text: str,
    sections: list[SectionAnchor],
) -> dict[str, str]:
    """Return mapping of section_number -> verbatim section text.

    Each section's text is from its heading start to the next section's start
    (or end-of-chapter for the last section). Sections that contain numbered
    subsections still get the intro/header material before the first subsection
    — that's content the LLM should explain.
    """
    if not sections:
        return {}

    positions: list[tuple[int, SectionAnchor]] = []
    for section in sections:
        pattern = _build_section_pattern(section.section_number)
        match = pattern.search(chapter_text)
        if match:
            positions.append((match.start(), section))
        else:
            logger.warning(
                "Section %s '%s' not found in chapter text",
                section.section_number,
                section.title,
            )

    positions.sort(key=lambda p: p[0])

    slices: dict[str, str] = {}
    for i, (start, section) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(chapter_text)
        slices[section.section_number] = chapter_text[start:end].strip()

    return slices


# ── Heading fallback (documents with NO numbered sections) ──────────────────
# Standards / articles / professional material use prose headings, not "12.1.1"
# numbering, so the regex anchor extractor finds nothing. When that happens we
# ask the LLM to mark the topic-boundary headings, slice the text by them, and
# synthesize sequential anchors so the normal per-section enrichment runs. This
# path is ONLY reached when zero numbered sections were found — numbered
# textbooks never hit it.

_HEADING_SEGMENTATION_SYSTEM = """\
You segment a chapter of teaching material into its natural TOPIC sections.

This chapter has NO numbered sections — only prose headings. List the headings \
that mark where one teachable topic ends and the next begins, in order, copied \
VERBATIM from the text (exact characters, so they can be located again).

Rules:
- Return the real section/topic headings only — the short, standalone titles \
that introduce a distinct idea (e.g. "Scope", "Identifying a lease", "Lessee \
accounting"). For Q&A material, each "Question N" is a heading.
- Copy each heading EXACTLY as it appears (same words, same case). Do not \
paraphrase, renumber, translate, or add punctuation.
- Order them top-to-bottom as they appear.
- Aim for the natural teaching units — typically 5 to 25. Not every line is a \
heading; skip ordinary body sentences.
- Return ONLY JSON: {"headings": ["...", "..."]}. No markdown, no commentary."""


def _build_heading_segmentation_prompt(chapter_title: str, chapter_text: str) -> str:
    return (
        f"Chapter: {chapter_title}\n\n"
        "List this chapter's topic headings, verbatim and in order.\n\n"
        "----- CHAPTER TEXT -----\n"
        f"{chapter_text}\n"
        "----- END CHAPTER TEXT -----"
    )


def _find_heading(text: str, heading: str, start: int) -> int:
    """Index of `heading` in `text` at/after `start`, or -1.

    Tries an exact substring match first (the LLM is asked to copy verbatim),
    then falls back to flexible-whitespace, case-insensitive matching so minor
    PDF spacing differences don't lose a heading.
    """
    h = heading.strip()
    if not h:
        return -1
    idx = text.find(h, start)
    if idx >= 0:
        return idx
    pattern = re.compile(r"\s+".join(re.escape(w) for w in h.split()), re.IGNORECASE)
    m = pattern.search(text, start)
    return m.start() if m else -1


class TopicExtractor:
    """One LLM call per section. Idempotent via existing_topic_ids."""

    MAX_RETRIES = 1
    MIN_SECTION_CHARS = 80

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    def extract_chapter_topics(
        self,
        chapter_text: str,
        chapter_title: str,
        chapter_index: int,
        anchors: ExtractionAnchors,
        skeleton: BookSkeleton | None,
        subject: str,
        existing_topic_ids: set[str] | None = None,
    ) -> tuple[list[Topic], TopicExtractionReport]:
        """Return (topics, report). Topics whose UID is in existing_topic_ids are skipped."""
        import time

        existing = existing_topic_ids or set()
        report = TopicExtractionReport()
        start = time.monotonic()

        sections = anchors.section_numbers
        if sections:
            section_text_map = slice_chapter_by_sections(chapter_text, sections)
        else:
            # No numbered sections (prose-heading doc — a standard, article,
            # professional material). Fall back to LLM heading segmentation so
            # the chapter still becomes topics. Gated on the numbered path being
            # empty, so numbered textbooks are completely unaffected.
            logger.info(
                "Chapter '%s' has no numbered sections — using LLM heading "
                "fallback for topic boundaries.",
                chapter_title,
            )
            sections, section_text_map = self._sections_from_headings(
                chapter_text, chapter_title
            )

        report.sections_seen = len(sections)
        if not sections:
            logger.warning(
                "Chapter '%s' produced no topic sections (numbered anchors AND "
                "heading fallback both empty) — skipping topic extraction.",
                chapter_title,
            )
            report.elapsed_seconds = time.monotonic() - start
            return [], report

        chapter_id = generate_chapter_uid(subject, chapter_title)
        topics: list[Topic] = []
        next_id: str | None = None

        for order, section in enumerate(reversed(sections), 1):
            section_text = section_text_map.get(section.section_number, "")
            within_order = len(sections) - order + 1

            topic_id = generate_topic_uid(
                subject, chapter_title, section.section_number
            )

            if topic_id in existing:
                logger.info(
                    "Topic %s already in graph — skipping enrichment",
                    section.section_number,
                )
                report.topics_skipped_existing += 1
                next_id = topic_id
                continue

            if len(section_text) < self.MIN_SECTION_CHARS:
                logger.warning(
                    "Section %s '%s' has only %d chars — extracting with thin content",
                    section.section_number,
                    section.title,
                    len(section_text),
                )

            try:
                our_understanding, examples, book_examples = self._enrich_section(
                    skeleton,
                    chapter_title,
                    section,
                    section_text,
                )
            except Exception as e:
                logger.exception(
                    "Topic extraction failed for %s '%s'",
                    section.section_number,
                    section.title,
                )
                report.topics_failed += 1
                report.failures.append(f"{section.section_number}: {e}")
                continue

            topic = Topic(
                topic_id=topic_id,
                chapter_id=chapter_id,
                section_number=section.section_number,
                within_chapter_order=within_order,
                topic_name=section.title,
                orig_book_content=section_text,
                our_understanding=our_understanding,
                examples=examples,
                book_examples=book_examples,
                next_topic_id=next_id,
            )
            topics.append(topic)
            next_id = topic_id
            report.topics_extracted += 1

        topics.reverse()

        report.elapsed_seconds = time.monotonic() - start
        logger.info(report.summary())
        return topics, report

    def _sections_from_headings(
        self, chapter_text: str, chapter_title: str
    ) -> tuple[list[SectionAnchor], dict[str, str]]:
        """Segment a non-numbered chapter into topics via LLM-detected headings.

        Returns synthetic sequential SectionAnchors ('1', '2', ...) plus a
        section_number -> text map, so the shared per-section loop runs
        unchanged. Empty result if the LLM finds no usable headings.
        """
        headings = self._detect_headings_llm(chapter_text, chapter_title)
        if not headings:
            return [], {}

        # Locate each heading in order; a sequential cursor handles repeated
        # heading strings without mismatching, and preserves document order.
        positions: list[tuple[int, str]] = []
        cursor = 0
        for h in headings:
            idx = _find_heading(chapter_text, h, cursor)
            if idx < 0:
                logger.warning(
                    "Heading %r not located in chapter text — skipping", h[:60]
                )
                continue
            positions.append((idx, h))
            cursor = idx + len(h)

        if not positions:
            return [], {}
        positions.sort(key=lambda p: p[0])

        sections: list[SectionAnchor] = []
        section_text_map: dict[str, str] = {}
        for i, (sec_start, heading) in enumerate(positions):
            end = positions[i + 1][0] if i + 1 < len(positions) else len(chapter_text)
            num = str(i + 1)
            sections.append(
                SectionAnchor(section_number=num, title=heading.strip()[:120], depth=1)
            )
            section_text_map[num] = chapter_text[sec_start:end].strip()

        logger.info(
            "Heading fallback segmented '%s' into %d topics.",
            chapter_title,
            len(sections),
        )
        return sections, section_text_map

    def _detect_headings_llm(self, chapter_text: str, chapter_title: str) -> list[str]:
        """Ask the LLM for the chapter's topic headings (verbatim, in order)."""
        system = _HEADING_SEGMENTATION_SYSTEM
        user = _build_heading_segmentation_prompt(chapter_title, chapter_text)
        try:
            response = self.llm.generate_json(system, user)
            data = json.loads(response.content)
        except Exception as e:  # noqa: BLE001 — any failure → empty, caller handles
            logger.warning("Heading detection LLM call failed: %s", e)
            return []
        raw = data.get("headings") if isinstance(data, dict) else data
        if not isinstance(raw, list):
            logger.warning("Heading detection returned no 'headings' list")
            return []
        seen: set[str] = set()
        headings: list[str] = []
        for h in raw:
            s = str(h).strip()
            if s and s.lower() not in seen:
                seen.add(s.lower())
                headings.append(s)
        return headings[:40]

    def _enrich_section(
        self,
        skeleton: BookSkeleton | None,
        chapter_title: str,
        section: SectionAnchor,
        section_text: str,
    ) -> tuple[str, list[str], list[BookExample]]:
        system_prompt = get_topic_system_prompt()
        user_prompt = build_topic_user_prompt(
            book_skeleton=skeleton,
            chapter_title=chapter_title,
            section_number=section.section_number,
            section_title=section.title,
            section_text=section_text,
        )

        last_error: Exception | None = None
        raw = ""
        for attempt in range(self.MAX_RETRIES + 1):
            response = self.llm.generate_json(system_prompt, user_prompt)
            raw = response.content
            if response.usage:
                logger.debug(
                    "Topic LLM call %s (attempt %d): in=%s out=%s",
                    section.section_number,
                    attempt + 1,
                    response.usage.get("input_tokens", "?"),
                    response.usage.get("output_tokens", "?"),
                )
            try:
                data = json.loads(raw)
                our_understanding = (data.get("our_understanding") or "").strip()
                examples_raw = data.get("examples") or []
                if not isinstance(examples_raw, list):
                    raise ValueError("'examples' must be a list")
                examples = [str(e).strip() for e in examples_raw if str(e).strip()]
                book_examples = _parse_book_examples(data.get("book_examples") or [])
                if not our_understanding:
                    raise ValueError("'our_understanding' is empty")
                return our_understanding, examples, book_examples
            except (json.JSONDecodeError, ValueError) as e:
                last_error = e
                logger.warning(
                    "Topic JSON parse failed for %s (attempt %d/%d): %s",
                    section.section_number,
                    attempt + 1,
                    self.MAX_RETRIES + 1,
                    e,
                )

        raise TopicExtractionError(
            f"LLM returned invalid topic JSON after {self.MAX_RETRIES + 1} attempts: {last_error}",
            raw_response=raw,
        )
