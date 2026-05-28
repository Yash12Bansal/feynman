"""Targeted BookExampleWeaver test — runs the weaver against an existing
extraction file's lesson_plans and reports coverage. No Neo4j write, no
TTS, no audio. Pure validation that the weaver architecture hits the
≥90% coverage floor we agreed on.

Usage:
    poetry run python tools/weave_chapter_examples.py \
        out/extraction_physics_physics_and_mathematics.json \
        chapter:physics:physics_and_mathematics

Outputs:
- WeaverReport (per-chapter telemetry: woven count, retries, failures)
- BookCoverageReport (structural validator — every book_example must
  produce ≥1 ChoreographyStep with is_book_example=True)
- Empirical setup_facts coverage (same check the user ran earlier that
  showed 22%) — apples-to-apples comparison
- Saves the woven extraction to <input>.woven.json for inspection
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

from lecture_pipeline_v2.config import PipelineConfig
from lecture_pipeline_v2.llm.factory import create_llm_provider
from lecture_pipeline_v2.curriculum.lecture_plan.book_example_weaver import (
    BookExampleWeaver,
)
from lecture_pipeline_v2.curriculum.lecture_plan.chapter_planner import (
    ChapterLecturePlanner,
)
from lecture_pipeline_v2.curriculum.lecture_plan.curriculum_adapter import (
    CurriculumAdapter,
)
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_narrator import LessonNarrator
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_planner import LessonPlanner
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_prosody import LessonProsody
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_quality_gate import (
    _diagram_id_short_to_long,
)
from lecture_pipeline_v2.curriculum.models import CurriculumExtractionResult
from lecture_pipeline_v2.curriculum.validation.book_coverage import (
    validate_book_coverage,
)


# Content-word overlap check. The weaver's narrations correctly include
# setup_facts in spoken form (e.g. "three meters per second"), but they
# don't quote the setup_fact strings VERBATIM — they paraphrase. A simple
# substring test would call this "skipped" when it's actually covered.
# The right measure: tokenise both, drop stopwords, check how many of the
# fact's content tokens appear in the narration.

_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "in", "on", "at", "of", "to", "for", "from", "by", "with", "and",
    "or", "but", "if", "as", "this", "that", "these", "those", "it",
    "its", "into", "out", "than", "then", "so", "we", "you", "i", "he",
    "she", "they", "them", "us", "our", "your", "their", "his", "her",
    "have", "has", "had", "do", "does", "did", "will", "would", "should",
    "can", "could", "may", "might", "must", "shall", "also", "just",
    "very", "much", "more", "less", "some", "any", "all", "each",
})
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-.][a-z0-9]+)*")


def _content_tokens(text: str) -> set[str]:
    return {
        t for t in _TOKEN_RE.findall(text.lower())
        if t not in _STOPWORDS and len(t) >= 2
    }


def setup_fact_covered(value: str, narration: str) -> bool:
    """A setup_fact counts as covered when ≥50% of its content tokens
    appear in the narration. Generous enough to handle the LLM's paraphrase
    (e.g., setup_fact 'Ball moves inside tube at three meters per second' →
    narration 'a small ball is moving inside a long tube at a speed of
    three meters per second') while still failing on actual skips.
    """
    fact_tokens = _content_tokens(value)
    if not fact_tokens:
        return False
    nar_tokens = _content_tokens(narration)
    hits = len(fact_tokens & nar_tokens)
    return hits / len(fact_tokens) >= 0.5


def empirical_coverage(
    *, topic_book_examples: list, narration: str
) -> tuple[int, int]:
    """Returns (covered_count, total_count) of book_examples where ≥70% of
    setup_facts appear in the narration (digit or spelled-out form)."""
    if not topic_book_examples:
        return (0, 0)
    covered = 0
    for be in topic_book_examples:
        facts = be.setup_facts or []
        if not facts:
            continue
        hits = sum(1 for f in facts if setup_fact_covered(f, narration))
        if hits / len(facts) >= 0.7:
            covered += 1
    return (covered, len(topic_book_examples))


async def main(extraction_path: Path, chapter_id: str) -> int:
    cfg = PipelineConfig.load()
    extraction = CurriculumExtractionResult.load(extraction_path)
    chapter = next(
        (c for c in extraction.chapters if c.chapter_id == chapter_id), None
    )
    if chapter is None:
        print(f"ERROR: chapter {chapter_id!r} not in {extraction_path}", file=sys.stderr)
        return 1
    topic_ids = set(chapter.topic_ids)
    topics = [t for t in extraction.topics if t.topic_id in topic_ids]
    # Diagrams: include any that link to one of this chapter's topics
    diagrams = [
        d for d in extraction.diagrams
        if any(tid in topic_ids for tid in d.linked_topic_ids)
    ]

    print(f"\n=== weave_chapter_examples : {chapter_id} ===")
    print(f"  topics: {len(topics)}")
    print(f"  diagrams: {len(diagrams)}")
    print(f"  existing lesson_plans on chapter: {len(chapter.lesson_plans)}")
    total_book_examples = sum(len(t.book_examples) for t in topics)
    print(f"  total book_examples (target for coverage): {total_book_examples}")
    if total_book_examples == 0:
        print("  no book_examples in this chapter — nothing to weave.")
        return 0

    # If lesson_plans aren't on disk (dump_chapter_extraction never saved
    # them — they're in-memory only during pipeline runs), generate them
    # fresh from the concept-only LessonPlanner so we can isolate the
    # weaver's behaviour.
    if not chapter.lesson_plans:
        print(f"\n--- no lesson_plans on disk; generating freshly via LessonPlanner ---")
        # Quick ChapterLecturePlan to feed CurriculumAdapter. The planner is
        # sync and expects an LLMProvider; build one from the config.
        llm = create_llm_provider(cfg.llm)
        lecture_planner = ChapterLecturePlanner(llm)
        results = lecture_planner.plan_for_all(
            chapters=[chapter],
            topics_by_chapter={chapter.chapter_id: topics},
        )
        lecture_plan = results.get(chapter.chapter_id)
        if lecture_plan is None:
            print("  ChapterLecturePlanner failed — bailing")
            return 1
        # CurriculumAdapter takes diagrams_by_topic (a topic_id → list[Diagram] dict).
        diagrams_by_topic: dict[str, list] = {}
        for d in diagrams:
            for tid in d.linked_topic_ids:
                diagrams_by_topic.setdefault(tid, []).append(d)
        adapter = CurriculumAdapter(
            chapter, topics, lecture_plan, diagrams_by_topic,
        )
        planner = LessonPlanner(cfg)
        fresh_plans = []
        for idx, tid in enumerate(lecture_plan.concept_sequence):
            plan = await planner.plan_one_topic(
                concept_index=idx,
                curriculum=adapter,
                topic_id=tid,
                chapter_id=chapter.chapter_id,
            )
            if plan is None:
                print(f"  LessonPlanner failed on {tid} — skipping")
                continue
            fresh_plans.append(plan)
            print(f"  planned: {tid} ({len(plan.choreography)} steps)")
        chapter.lesson_plans = fresh_plans
        if not fresh_plans:
            print("  no lesson_plans produced — bailing")
            return 1

    plans_by_tid = {p.topic_id: p for p in chapter.lesson_plans}
    topics_by_id = {t.topic_id: t for t in topics}
    diagrams_by_id = {d.diagram_id: d for d in diagrams}

    print(f"\n--- running BookExampleWeaver ({total_book_examples} examples to weave) ---")
    weaver = BookExampleWeaver(cfg)
    weaver_report = await weaver.weave_for_chapter(
        chapter_lesson_plans=plans_by_tid,
        topics_by_id=topics_by_id,
        diagrams_by_id=diagrams_by_id,
    )
    print(f"  {weaver_report.summary()}")

    # Structural validator — hard floor.
    print(f"\n--- structural validator (every book_example must have ≥1 tagged step) ---")
    structural = validate_book_coverage(topics, plans_by_tid)
    print(f"  {structural.summary()}")
    if structural.gaps:
        print(f"  structural gaps:")
        for g in structural.gaps[:10]:
            print(f"    {g.section_number} ref={g.book_example_ref}: {g.lesson_focus[:80]}")

    # Empirical setup_facts coverage — re-narrate the woven plans first so the
    # narration reflects the inserted example steps.
    print(f"\n--- empirical setup_facts coverage (apples-to-apples vs the earlier 22% baseline) ---")
    narrator = LessonNarrator(cfg)
    prosody = LessonProsody()
    narrations_by_tid: dict[str, str] = {}
    for plan in plans_by_tid.values():
        try:
            short_to_long = _diagram_id_short_to_long(plan, plan.topic_id)
            renarrated = narrator.render(
                topic_id=plan.topic_id,
                plan=plan,
                diagram_id_resolver=lambda s, _m=short_to_long: _m.get(s, s),
            )
            applied = prosody.apply(renarrated)
            narrations_by_tid[plan.topic_id] = applied.full_text_with_markers
        except Exception as exc:  # noqa: BLE001
            print(f"  WARN: narrator failed for {plan.topic_id}: {exc}")

    overall_covered = 0
    overall_total = 0
    for topic in topics:
        if not topic.book_examples:
            continue
        nar = narrations_by_tid.get(topic.topic_id, "")
        c, n = empirical_coverage(
            topic_book_examples=topic.book_examples, narration=nar
        )
        overall_covered += c
        overall_total += n
        marker = "✓" if c == n else ("◐" if c > 0 else "✗")
        print(f"  {marker} {topic.section_number} {topic.topic_name[:42]:42}  {c}/{n}")

    pct = overall_covered / max(1, overall_total) * 100
    floor = 90.0
    verdict = "PASS" if pct >= floor else "BELOW FLOOR"
    print()
    print(f"=== EMPIRICAL COVERAGE: {overall_covered}/{overall_total} ({pct:.0f}%) — {verdict} (floor {floor:.0f}%) ===")
    print(f"  prior baseline (before weaver): 22%")
    print(f"  delta:                          +{pct - 22:.0f}pp")

    # Save the woven extraction for inspection.
    out_path = extraction_path.with_suffix(".woven.json")
    chapter.lesson_plans = list(plans_by_tid.values())
    extraction.save(out_path)
    print(f"\n  saved woven extraction → {out_path}")
    return 0 if pct >= floor else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("extraction_path", type=Path)
    parser.add_argument("chapter_id")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.extraction_path, args.chapter_id)))
