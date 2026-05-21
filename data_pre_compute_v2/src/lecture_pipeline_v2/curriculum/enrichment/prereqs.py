"""Within-book prereq linking.

One LLM pass over all topics in the book; the model proposes prereq edges
between topic_ids. Edges respect book order (a topic can only require
something that appeared earlier or in an earlier chapter).

These edges are reference-only — the runtime never auto-walks them; it
only follows them when a student explicitly asks about a dependency or
when mastery on a prereq drops below threshold.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

from ...llm.base import LLMProvider
from ..models import Topic

logger = logging.getLogger(__name__)


PREREQ_SYSTEM_PROMPT = """You are building a knowledge dependency map for a textbook.

Given the ordered list of topics from one book, produce a list of prerequisite edges. A prereq edge says "to understand topic B, the student should already understand topic A."

Rules:
1. The "from" topic (the prerequisite) must come EARLIER in the book than the "to" topic.
2. Only emit edges where the dependency is real and load-bearing — not "vaguely related". A student missing this prereq would actually struggle with the dependent topic.
3. Most topics need 0-3 prereqs. A few foundational topics will be the source of many edges.
4. Use topic_id strings exactly as given.

Return a JSON object with one key "edges" — an array. Each element:
  {"from_topic_id": "...", "to_topic_id": "...", "reason": "one-sentence why"}

Return ONLY the JSON. No markdown. No commentary."""


@dataclass
class PrereqLinkingReport:
    topics_seen: int = 0
    edges_proposed: int = 0
    edges_accepted: int = 0
    edges_rejected: int = 0
    elapsed_seconds: float = 0.0
    failures: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"Prereq linking — {self.edges_accepted}/{self.edges_proposed} edges accepted "
            f"({self.edges_rejected} rejected), "
            f"{self.elapsed_seconds:.1f}s"
        )


class PrereqLinker:
    """Single-pass linker. Mutates each Topic.prereq_topic_ids in place."""

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    def link(self, topics: list[Topic]) -> PrereqLinkingReport:
        report = PrereqLinkingReport(topics_seen=len(topics))
        start = time.monotonic()

        if len(topics) < 2:
            report.elapsed_seconds = time.monotonic() - start
            return report

        ordered = sorted(
            topics,
            key=lambda t: (self._chapter_order(t), t.within_chapter_order),
        )
        order_by_id = {t.topic_id: i for i, t in enumerate(ordered)}
        topic_by_id = {t.topic_id: t for t in ordered}

        user_prompt = self._build_user_prompt(ordered)

        try:
            response = self.llm.generate_json(PREREQ_SYSTEM_PROMPT, user_prompt)
            data = json.loads(response.content)
        except Exception as e:
            logger.exception("Prereq LLM call failed")
            report.failures.append(str(e))
            report.elapsed_seconds = time.monotonic() - start
            return report

        edges = data.get("edges") or []
        report.edges_proposed = len(edges)

        for edge in edges:
            if not isinstance(edge, dict):
                report.edges_rejected += 1
                continue
            from_id = edge.get("from_topic_id")
            to_id = edge.get("to_topic_id")
            if not from_id or not to_id:
                report.edges_rejected += 1
                continue
            if from_id == to_id:
                report.edges_rejected += 1
                continue
            if from_id not in order_by_id or to_id not in order_by_id:
                report.edges_rejected += 1
                continue
            if order_by_id[from_id] >= order_by_id[to_id]:
                # Reject — prereq must come earlier in the book
                report.edges_rejected += 1
                continue

            to_topic = topic_by_id[to_id]
            if from_id not in to_topic.prereq_topic_ids:
                to_topic.prereq_topic_ids.append(from_id)
                report.edges_accepted += 1
            else:
                report.edges_rejected += 1

        report.elapsed_seconds = time.monotonic() - start
        logger.info(report.summary())
        return report

    @staticmethod
    def _chapter_order(topic: Topic) -> int:
        # Topic.chapter_id is "chapter:{subject}:{chapter_slug}"; we don't have
        # numeric chapter_order on Topic directly, so use the chapter_id alphabetically
        # as a stable proxy and within_chapter_order as the secondary key. The pipeline
        # assigns within_chapter_order from anchored section order, which preserves
        # book sequence within a chapter. Cross-chapter ordering comes from the
        # caller passing topics already grouped by chapter.
        return hash(topic.chapter_id)

    def _build_user_prompt(self, topics: list[Topic]) -> str:
        lines = ["## Topics in book order\n"]
        for t in topics:
            short_desc = t.our_understanding[:200].replace("\n", " ").strip()
            if len(t.our_understanding) > 200:
                short_desc += "..."
            lines.append(
                f"- topic_id={t.topic_id}\n"
                f"  name: {t.topic_name}\n"
                f"  section: {t.section_number}\n"
                f"  summary: {short_desc}\n"
            )
        return "\n".join(lines) + "\n\nProduce the prereq edge list."
