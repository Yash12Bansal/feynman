"""TopicExtractor heading fallback — topics from prose-heading (non-numbered) docs.

When the regex anchor extractor finds 0 numbered sections (standards, articles,
professional material — e.g. ICAI Ind AS), the extractor asks an LLM for the
topic headings, slices the text by them, and synthesizes sequential anchors so
the normal per-section enrichment runs. Numbered textbooks must NEVER hit this
path. Both covered here with a fake LLM (no network).
"""

from __future__ import annotations

import json

from lecture_pipeline_v2.curriculum.anchors.models import (
    ExtractionAnchors,
    SectionAnchor,
)
from lecture_pipeline_v2.curriculum.topic_extractor import (
    _HEADING_SEGMENTATION_SYSTEM,
    TopicExtractor,
)
from lecture_pipeline_v2.llm.base import LLMResponse


class _FakeLLM:
    """Returns canned JSON payloads from a queue; records each call's system
    prompt so tests can assert which path ran."""

    def __init__(self, queue: list[dict]) -> None:
        self._queue = list(queue)
        self.systems: list[str] = []

    def generate_json(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        self.systems.append(system_prompt)
        payload = self._queue.pop(0)
        return LLMResponse(content=json.dumps(payload), model="fake")


_ENRICH = {
    "our_understanding": "A clear, complete explanation of the idea.",
    "examples": ["a concrete example"],
    "book_examples": [],
}


def test_heading_fallback_builds_topics_when_no_numbered_sections() -> None:
    chapter_text = (
        "Some introduction prose before any heading.\n\n"
        "Scope\n"
        "This standard applies to all leases except a few carve-outs and so on.\n\n"
        "Identifying a lease\n"
        "A contract is or contains a lease if it conveys the right to control use.\n"
    )
    llm = _FakeLLM(
        [
            {"headings": ["Scope", "Identifying a lease"]},  # heading detection
            _ENRICH,  # enrichment (loop runs reversed; payloads are generic)
            _ENRICH,
        ]
    )
    extractor = TopicExtractor(llm)
    anchors = ExtractionAnchors(section_numbers=[])  # NONE → triggers fallback

    topics, report = extractor.extract_chapter_topics(
        chapter_text=chapter_text,
        chapter_title="Ind AS 116 Leases",
        chapter_index=1,
        anchors=anchors,
        skeleton=None,
        subject="accounting",
    )

    assert [t.topic_name for t in topics] == ["Scope", "Identifying a lease"]
    assert [t.section_number for t in topics] == ["1", "2"]
    assert report.topics_extracted == 2
    # Each topic carries its own sliced text, in order.
    assert "applies to all leases" in topics[0].orig_book_content
    assert "right to control use" in topics[1].orig_book_content
    # The fallback's heading-detection prompt WAS used.
    assert _HEADING_SEGMENTATION_SYSTEM in llm.systems


def test_numbered_sections_never_trigger_heading_fallback() -> None:
    chapter_text = (
        "1.1 Scope\n"
        "This standard applies to all leases except a few carve-outs.\n\n"
        "1.2 Identifying a lease\n"
        "A contract is or contains a lease if it conveys the right to control use.\n"
    )
    # ONLY enrichment payloads queued — no heading-detection response. If the
    # fallback wrongly ran it would consume _ENRICH (no "headings") → 0 topics.
    llm = _FakeLLM([_ENRICH, _ENRICH])
    extractor = TopicExtractor(llm)
    anchors = ExtractionAnchors(
        section_numbers=[
            SectionAnchor(section_number="1.1", title="Scope", depth=2),
            SectionAnchor(section_number="1.2", title="Identifying a lease", depth=2),
        ]
    )

    topics, report = extractor.extract_chapter_topics(
        chapter_text=chapter_text,
        chapter_title="Leases",
        chapter_index=1,
        anchors=anchors,
        skeleton=None,
        subject="accounting",
    )

    assert [t.section_number for t in topics] == ["1.1", "1.2"]
    assert report.topics_extracted == 2
    # Heading fallback must NOT have run.
    assert _HEADING_SEGMENTATION_SYSTEM not in llm.systems
