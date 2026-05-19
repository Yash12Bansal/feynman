"""Per-chapter lecture-script generation — Path C.

One LLM call per chapter. Given all topics in book order (with their
our_understanding, examples, and diagram descriptions), the model emits
TWO narrations per topic AND populates a notebook (the right-hand panel of
SplitBoard) with structured entries — equations, steps, key points, etc.

Both narrations are richly annotated with inline markers that the pipeline
chunker parses into manifest events:

  Slide-side:
    <<SHOW_DIAGRAM:diagram_id>>        render the diagram on the slide panel

  Notebook-side (NEW):
    <<SECTION:title>>                   write a section header on the notebook
    <<WRITE_EQUATION:LaTeX|group=A>>    write a LaTeX equation (optional align_group)
    <<WRITE_STEP:text|indent=1>>        write a numbered/bulleted step
    <<WRITE_KEY:text>>                  write a boxed key takeaway
    <<WRITE_TEXT:text>>                 write plain prose on the notebook
    <<WRITE_ANSWER:text>>               write a highlighted final answer
    <<STRIKE:id>>                       cross out a previously-written entry
    <<NEW_PAGE>>                        turn the notebook page

  Timing:
    <<PAUSE:short>>                     ~250ms pause for emphasis
    <<PAUSE:long>>                      ~750ms pause between major beats
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field

from ...llm.base import LLMProvider
from ..models import Chapter, Diagram, Topic

logger = logging.getLogger(__name__)


# Valid characters that may follow a backslash in a JSON string literal:
#   "  \  /  b  f  n  r  t  u
# Anything else is illegal — and LaTeX commands like \vec, \theta, \frac,
# \cos, \sin, \,  are EXACTLY the case we hit when narration text embeds
# <<WRITE_EQUATION:...>> markers. Claude often forgets to double-escape.
# Sanitiser doubles any bare backslash whose next char isn't a JSON escape.
_BAD_BACKSLASH_RE = re.compile(r'\\(?=[^"\\/bfnrtu])')


def _sanitize_latex_backslashes(raw: str) -> str:
    """Pre-process the LLM's JSON to fix bare LaTeX backslashes.

    Claude sometimes emits `\\vec` (one backslash) inside JSON string values.
    JSON only accepts a specific set of escapes — so the parser fails. We
    sweep through and double any `\\` whose next character isn't already a
    valid JSON escape token, leaving valid escapes (\\n, \\", \\\\) untouched.
    """
    return _BAD_BACKSLASH_RE.sub(r"\\\\", raw)


SCRIPT_SYSTEM_PROMPT = """You are writing a complete spoken lecture for one chapter of a textbook, with simultaneous board notation. The voice will be TTS'd; the marked-up board entries will appear on a "notebook" panel beside the slide — exactly as a real teacher writes things down while speaking.

Speak like an excellent teacher at a whiteboard — warm, clear, intellectually honest. Concrete examples. Direct address. No filler.

You will write TWO narrations for EACH topic in the chapter:

1. narration_chapter — flows from the previous topic into this one and into the next. Use natural transitions: "Now that we've seen X, let's move on to Y." "We'll come back to this in a moment." For the first topic, open the chapter naturally. For the last, close it and tee up the next chapter.

2. narration_standalone — self-contained. Imagine the student lands here directly with no prior context. Open with something like "In this section, we look at..." End cleanly, without referring to other sections.

Both narrations are written for SPEECH. Speak equations in words ("velocity equals u plus a times t", NOT "v = u + at"). No section/figure/page references in the spoken text — refer to diagrams conversationally ("look at the board for a moment"). No markdown formatting.

# Inline markers (REQUIRED)

Embed these directly in the narration string at the exact point where they should fire:

## Slide-side
  <<SHOW_DIAGRAM:diagram_id>>
      The diagram_id MUST come from the diagrams list provided.
      Place this RIGHT BEFORE the sentence where you reference it
      ("let me show you on the board"). The slide cross-fades to the new diagram.

## Notebook-side (this is what makes it a classroom, not a podcast)

  <<SECTION:title>>
      Bold section header written across the top of the notebook.
      Use this AT MOST ONCE per topic, near the very beginning,
      to anchor what the student should be paying attention to.

  <<WRITE_EQUATION:LaTeX>>
  <<WRITE_EQUATION:LaTeX|group=alignA>>
      Write a LaTeX equation in the notebook. Use this when you're saying
      something the teacher would write down — laws, definitions, results.
      LaTeX must be valid KaTeX. Examples:
        <<WRITE_EQUATION:\\vec{F} = m\\vec{a}>>
        <<WRITE_EQUATION:E_k = \\tfrac{1}{2}mv^2>>
      When you have a derivation chain, put related equations in the SAME
      align group so they line up at the equals sign:
        <<WRITE_EQUATION:F = ma|group=g1>>
        <<WRITE_EQUATION:5 = 2a|group=g1>>
        <<WRITE_EQUATION:a = 2.5\\,\\text{m/s}^2|group=g1>>

  <<WRITE_STEP:text>>
  <<WRITE_STEP:text|indent=1>>
      A numbered/bulleted step in a derivation or worked example.
      indent is 0–3; default 0. Use indent for sub-steps.
      Example: <<WRITE_STEP:First, identify all the forces on the block>>

  <<WRITE_KEY:text>>
      A boxed key takeaway. Use for the central insight a student MUST
      remember. Maximum one or two per topic. Example:
        <<WRITE_KEY:An object at rest stays at rest unless acted on by a net force.>>

  <<WRITE_TEXT:text>>
      Plain prose written on the notebook — a brief annotation, a definition
      in words, a label. Less weight than KEY; more flow than STEP.

  <<WRITE_ANSWER:text>>
      Highlighted final answer. Use ONLY when a worked problem culminates
      in a concrete numerical or symbolic result.

  <<STRIKE:id>>
      Cross out an earlier entry (e.g., to mark a wrong path you considered).
      'id' is the id you assigned in a previous marker — see "IDs" below.

  <<NEW_PAGE>>
      Turn the notebook page. Use SPARINGLY — only when the notebook is
      genuinely full (think: 8+ entries). Most topics won't need this.

## Timing
  <<PAUSE:short>>     ~250ms pause for emphasis (after important sentences)
  <<PAUSE:long>>      ~750ms pause between major beats

# IDs for notebook markers

Every notebook marker that creates an entry (SECTION/WRITE_EQUATION/WRITE_STEP/
WRITE_KEY/WRITE_TEXT/WRITE_ANSWER) needs a stable id so STRIKE can target it.
Use simple readable ids like "eq-1", "step-1", "key-1", "section-1" — number
them sequentially WITHIN a topic. The id is encoded after the content with a
pipe:

  <<WRITE_EQUATION:F = ma|id=eq-1>>
  <<WRITE_STEP:Identify the forces|id=step-1>>
  <<WRITE_KEY:Force causes acceleration|id=key-1>>

If you omit |id=..., the chunker will auto-generate one — but you can't
STRIKE it later, so explicit ids are required if you plan to strike.

# HARD rules (read carefully)

1. **Diagrams MUST appear early in each topic.** Place the first
   <<SHOW_DIAGRAM>> for a topic within its FIRST 20 SECONDS of audio
   (≈ the first 50 spoken words). A teacher draws the picture FIRST, then
   explains. Do NOT back-load diagrams.

2. **Notebook fills as the voice speaks.** Every topic gets at minimum:
     - 1 <<SECTION:>> at the top, AND
     - 2–5 of (<<WRITE_EQUATION>>, <<WRITE_STEP>>, <<WRITE_KEY>>,
       <<WRITE_TEXT>>) sprinkled through the narration where a teacher
       would naturally write.
   Topics with no diagrams need MORE notebook entries — that's where the
   teaching happens on the board.

3. **Markers are inline, not separate fields.** Embed them DIRECTLY in the
   narration_chapter / narration_standalone strings. Order matters — the
   sequence in the string IS the playback order.

4. **Both narrations need their own markers.** The chapter and standalone
   versions are separate strings; mark them up independently. They may emit
   different notebooks (the chapter version inherits some context from the
   previous topic; the standalone is fresh).

5. **No symbolic equations in the spoken text.** Equations live ONLY inside
   <<WRITE_EQUATION:...>> markers. The spoken sentence around them says it
   in words: "We get... <<WRITE_EQUATION:F = ma|id=eq-1>> ...force equals
   mass times acceleration."

6. **Reference only diagram_ids that exist** in the provided list for that
   topic. Never invent ids.

# Output format

Return a JSON object with one key "segments" — array, one element per topic
in book order:

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

- segments must cover EVERY topic, in the order given.
- topic_id must match exactly.
- Return ONLY the JSON. No markdown fences. No commentary."""


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
            raw = response.content
            # Claude occasionally forgets to double-escape LaTeX backslashes
            # inside JSON strings (e.g., emits `\vec` instead of `\\vec`).
            # First try parsing as-is; fall back to sanitised version.
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as e:
                logger.warning(
                    "Lecture-script JSON parse failed at pos %d (%s) — "
                    "retrying with LaTeX-backslash sanitiser",
                    e.pos, e.msg,
                )
                data = json.loads(_sanitize_latex_backslashes(raw))
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
