"""Per-chapter lecture-script generation.

One LLM call per chapter. Given all topics in book order (with their
our_understanding, examples, and diagram descriptions), the model emits
TWO narrations per topic:

  - narration_chapter: with transitions to/from the surrounding topics
    ("Now that we have X, let's see Y" / "We'll come back to this in a moment")
  - narration_standalone: self-contained for direct-ask / interrupt playback
    ("In this section, we look at...")

Both narrations include inline markers:
  <<SHOW_DIAGRAM:diagram_id>> — render the diagram now
  <<PAUSE:short>> / <<PAUSE:long>> — insert a natural pause
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

from ...llm.base import LLMProvider
from ..models import Chapter, Diagram, Topic

logger = logging.getLogger(__name__)


SCRIPT_SYSTEM_PROMPT = """You are writing a complete spoken lecture for one chapter of a textbook. The lecture will be read aloud to a student by a TTS engine.

Speak like an excellent teacher at a whiteboard — warm, clear, intellectually honest. Concrete examples. Direct address. No filler.

You will write TWO narrations for EACH topic in the chapter:

1. narration_chapter — flows from the previous topic into this one, and into the next. Use natural transitions: "Now that we've seen X, let's move on to Y." "We'll come back to this in a moment." For the first topic in the chapter, open the chapter naturally. For the last, close the chapter and tee up the next.

2. narration_standalone — self-contained. Imagine the student lands here directly with no prior context. Open with something like "In this section, we look at..." End cleanly, without referring to other sections.

Both narrations are written for SPEECH. No equations in symbols — write them out in words. No section/figure/page references — just refer to diagrams conversationally. No markdown.

Embed these inline markers in the narration text:

  <<SHOW_DIAGRAM:diagram_id>>
      Place this where you say "let me show you on the board" or refer to the visual.
      The diagram_id must come from the diagrams list provided.
  <<PAUSE:short>>
      ~250ms pause. Use after important sentences, before a transition.
  <<PAUSE:long>>
      ~750ms pause. Use between major beats (e.g., before introducing a new idea).

Return a JSON object with one key "segments" — array, one element per topic in book order:

{
  "segments": [
    {
      "topic_id": "topic:...",
      "narration_chapter": "string with inline markers",
      "narration_standalone": "string with inline markers"
    },
    ...
  ]
}

Hard rules:
- segments must cover EVERY topic, in the order given.
- topic_id must match exactly.
- Reference only diagram_ids that exist in the provided list for that topic.
- Plain prose only. No markdown. No bullet points inside narration strings.
- Return ONLY the JSON. No commentary."""


@dataclass
class ScriptWriterReport:
    chapters_processed: int = 0
    segments_emitted: int = 0
    chapters_skipped_existing: int = 0
    failures: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    def summary(self) -> str:
        return (
            f"Lecture script — {self.segments_emitted} segments across "
            f"{self.chapters_processed} chapters, "
            f"{self.chapters_skipped_existing} chapters skipped (already scripted), "
            f"{len(self.failures)} failures, "
            f"{self.elapsed_seconds:.1f}s"
        )


@dataclass
class ChapterScript:
    """Result of one chapter's script-writing pass. Consumed by TTS layer."""

    chapter_id: str
    segments: list[dict]


class ScriptWriter:
    def __init__(self, llm: LLMProvider):
        self.llm = llm

    def write_for_chapter(
        self,
        chapter: Chapter,
        topics: list[Topic],
        diagrams_by_topic: dict[str, list[Diagram]],
    ) -> ChapterScript | None:
        if not topics:
            return None

        user_prompt = self._build_user_prompt(chapter, topics, diagrams_by_topic)

        try:
            response = self.llm.generate_json(SCRIPT_SYSTEM_PROMPT, user_prompt)
            data = json.loads(response.content)
        except Exception as e:
            logger.exception("Lecture script failed for chapter %s", chapter.chapter_id)
            raise

        segments_raw = data.get("segments") or []
        topic_ids = {t.topic_id for t in topics}
        accepted: list[dict] = []
        for seg in segments_raw:
            if not isinstance(seg, dict):
                continue
            tid = seg.get("topic_id")
            chap = (seg.get("narration_chapter") or "").strip()
            standalone = (seg.get("narration_standalone") or "").strip()
            if not tid or tid not in topic_ids:
                continue
            if not chap or not standalone:
                continue
            accepted.append({
                "topic_id": tid,
                "narration_chapter": chap,
                "narration_standalone": standalone,
            })

        if not accepted:
            logger.warning("Chapter %s produced no usable segments", chapter.chapter_id)
            return None

        return ChapterScript(chapter_id=chapter.chapter_id, segments=accepted)

    def write_for_all(
        self,
        chapters: list[Chapter],
        topics_by_chapter: dict[str, list[Topic]],
        diagrams_by_topic: dict[str, list[Diagram]],
        existing_chapter_ids_with_audio: set[str] | None = None,
    ) -> tuple[dict[str, ChapterScript], ScriptWriterReport]:
        already_scripted = existing_chapter_ids_with_audio or set()
        report = ScriptWriterReport()
        start = time.monotonic()

        out: dict[str, ChapterScript] = {}
        for chapter in chapters:
            if chapter.chapter_id in already_scripted:
                report.chapters_skipped_existing += 1
                continue
            chapter_topics = topics_by_chapter.get(chapter.chapter_id, [])
            if not chapter_topics:
                continue
            try:
                script = self.write_for_chapter(chapter, chapter_topics, diagrams_by_topic)
                if script:
                    out[chapter.chapter_id] = script
                    report.chapters_processed += 1
                    report.segments_emitted += len(script.segments)
            except Exception as e:
                report.failures.append(f"{chapter.chapter_id}: {e}")

        report.elapsed_seconds = time.monotonic() - start
        logger.info(report.summary())
        return out, report

    def _build_user_prompt(
        self,
        chapter: Chapter,
        topics: list[Topic],
        diagrams_by_topic: dict[str, list[Diagram]],
    ) -> str:
        sorted_topics = sorted(topics, key=lambda t: t.within_chapter_order)
        lines = [
            f"## Chapter: {chapter.title}\n",
            f"## Chapter summary\n{chapter.summary}\n",
            "## Topics (write segments in this order)\n",
        ]
        for t in sorted_topics:
            lines.append(f"### Topic {t.section_number}: {t.topic_name}")
            lines.append(f"topic_id: {t.topic_id}")
            lines.append(f"\nExplanation:\n{t.our_understanding}\n")
            if t.examples:
                lines.append("Examples:")
                for ex in t.examples:
                    lines.append(f"- {ex}")
                lines.append("")
            diags = diagrams_by_topic.get(t.topic_id, [])
            if diags:
                lines.append("Available diagrams for this topic:")
                for d in diags:
                    lines.append(f"- diagram_id={d.diagram_id} :: {d.description}")
            else:
                lines.append("(no diagrams)")
            lines.append("")

        lines.append(
            "Write two narrations per topic. Return ONLY the JSON with 'segments'."
        )
        return "\n".join(lines)
