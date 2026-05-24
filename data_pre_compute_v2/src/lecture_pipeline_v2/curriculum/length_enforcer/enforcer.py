"""Phase 4d — LengthEnforcer.

Deterministic chapter-length trim. Pure passes (drop, merge) — only Pass 3
calls back into `BeatNarrationWriter.rewrite`. Hard ceiling is never blocking:
over-ceiling chapters get flagged `needs_review` and accepted as-is.

Pass order (each pass re-evaluates the budget before the next):
  0. Within `budget * tolerance` → done.
  1. Drop all `beat_type == "summarize"` beats.
  2. Drop secondary `example` beats per topic (keep the first).
  3. Merge adjacent `explain`/`derive` beats within the same topic.
  4. Rewrite the longest non-structural beat with `target * 0.75`.

Non-deletable / non-rewritable beat types:
  STRUCTURAL = {hook, big_picture, first_principles, ask, misconception}
"""

from __future__ import annotations

import dataclasses
import logging

from feynman_teaching_kernel import ConceptTeachingPlan, TeachingBeat

from ...config import LengthEnforcerConfig
from ..beat_narration.models import BeatNarration
from ..models import Chapter, Topic

logger = logging.getLogger(__name__)

STRUCTURAL: frozenset[str] = frozenset(
    {"hook", "big_picture", "first_principles", "ask", "misconception"}
)


@dataclasses.dataclass
class LengthEnforcerReport:
    chapter_id: str
    initial_seconds: float
    final_seconds: float
    budget_seconds: float
    tolerance: float
    hard_ceiling: float
    dropped_beats: list[str] = dataclasses.field(default_factory=list)
    merged_pairs: list[tuple[str, str]] = dataclasses.field(default_factory=list)
    rewritten: list[str] = dataclasses.field(default_factory=list)
    needs_review: bool = False

    def summary(self) -> str:
        return (
            f"LengthEnforcer[{self.chapter_id}] "
            f"{self.initial_seconds:.0f}s -> {self.final_seconds:.0f}s "
            f"(budget {self.budget_seconds:.0f}s, "
            f"dropped={len(self.dropped_beats)}, merged={len(self.merged_pairs)}, "
            f"rewritten={len(self.rewritten)}, needs_review={self.needs_review})"
        )


class LengthEnforcer:
    def __init__(self, *, config: LengthEnforcerConfig) -> None:
        self.config = config

    async def trim(
        self,
        *,
        chapter: Chapter,
        rewriter: object
        | None = None,  # `BeatNarrationWriter`; loose-typed to dodge import cycle
        rewrite_context: dict[str, tuple[Topic, ConceptTeachingPlan, TeachingBeat]]
        | None = None,
    ) -> LengthEnforcerReport:
        narrations = chapter.beat_narrations or []
        budget = float(
            chapter.lecture_plan.length_budget_seconds if chapter.lecture_plan else 0
        )
        report = LengthEnforcerReport(
            chapter_id=chapter.chapter_id,
            initial_seconds=_total_seconds(narrations),
            final_seconds=0.0,
            budget_seconds=budget,
            tolerance=self.config.budget_tolerance,
            hard_ceiling=self.config.hard_ceiling,
        )
        if not narrations:
            return report
        if budget <= 0:
            # No budget set — accept whatever the writer produced.
            report.final_seconds = report.initial_seconds
            return report

        soft = budget * self.config.budget_tolerance
        hard = budget * self.config.hard_ceiling

        current = report.initial_seconds
        if current <= soft:
            report.final_seconds = current
            return report

        # ---- Pass 1: drop summarize ----
        kept: list[BeatNarration] = []
        for n in narrations:
            if n.beat_type == "summarize":
                report.dropped_beats.append(n.beat_id)
            else:
                kept.append(n)
        narrations = kept

        # ---- Pass 1.5: drop secondary examples per topic ----
        seen_example: set[str] = set()
        kept = []
        for n in narrations:
            if n.beat_type == "example":
                if n.topic_id in seen_example:
                    report.dropped_beats.append(n.beat_id)
                    continue
                seen_example.add(n.topic_id)
            kept.append(n)
        narrations = kept
        chapter.beat_narrations = narrations
        current = _total_seconds(narrations)
        if current <= soft:
            report.final_seconds = current
            return report

        # ---- Pass 2: merge adjacent explain/derive within the same topic ----
        merged: list[BeatNarration] = []
        MERGEABLE = {"explain", "derive"}
        for n in narrations:
            if (
                merged
                and merged[-1].topic_id == n.topic_id
                and merged[-1].beat_type in MERGEABLE
                and n.beat_type in MERGEABLE
            ):
                prev = merged[-1]
                report.merged_pairs.append((prev.beat_id, n.beat_id))
                prev.text = (prev.text.rstrip() + " " + n.text.lstrip()).strip()
                prev.estimated_duration_seconds += n.estimated_duration_seconds
                prev.target_duration_seconds += n.target_duration_seconds
                prev.audio_targets = sorted(
                    set(prev.audio_targets) | set(n.audio_targets)
                )
                prev.needs_review = prev.needs_review or n.needs_review
            else:
                merged.append(n)
        narrations = merged
        chapter.beat_narrations = narrations
        current = _total_seconds(narrations)
        if current <= soft:
            report.final_seconds = current
            return report

        # ---- Pass 3: rewrite longest non-structural beat ----
        if rewriter is not None and rewrite_context is not None:
            longest = _longest_non_structural(narrations)
            if longest is not None:
                ctx = rewrite_context.get(longest.beat_id)
                if ctx is not None:
                    topic, plan, beat = ctx
                    new_target = max(5, int(longest.target_duration_seconds * 0.75))
                    try:
                        rewritten = await rewriter.rewrite(  # type: ignore[attr-defined]
                            longest,
                            new_target_seconds=new_target,
                            topic=topic,
                            plan=plan,
                            beat=beat,
                        )
                    except Exception as e:  # noqa: BLE001
                        logger.warning(
                            "LengthEnforcer.rewrite_failed beat=%s err=%s",
                            longest.beat_id,
                            e,
                        )
                        rewritten = None
                    if rewritten is not None and rewritten.text:
                        longest.text = rewritten.text
                        longest.target_duration_seconds = new_target
                        longest.estimated_duration_seconds = (
                            rewritten.estimated_duration_seconds
                        )
                        longest.audio_targets = rewritten.audio_targets
                        longest.needs_review = (
                            longest.needs_review or rewritten.needs_review
                        )
                        report.rewritten.append(longest.beat_id)
                        current = _total_seconds(narrations)

        # ---- Hard ceiling check ----
        report.final_seconds = current
        if current > hard:
            logger.warning(
                "LengthEnforcer.over_ceiling chapter=%s %.0fs > %.0fs ceiling",
                chapter.chapter_id,
                current,
                hard,
            )
            report.needs_review = True
        return report


def _total_seconds(narrations: list[BeatNarration]) -> float:
    return sum(n.estimated_duration_seconds for n in narrations)


def _longest_non_structural(narrations: list[BeatNarration]) -> BeatNarration | None:
    candidates = [n for n in narrations if n.beat_type not in STRUCTURAL]
    if not candidates:
        return None
    return max(candidates, key=lambda n: n.estimated_duration_seconds)
