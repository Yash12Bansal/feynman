"""Deterministic ULQF metric collectors."""

from __future__ import annotations

import re
from collections import Counter

from lecture_pipeline_v2.curriculum.lecture_plan.lesson_plan_models import (
    LessonPlan,
    _FORBIDDEN_HOOK_OPENERS,
)
from lecture_pipeline_v2.curriculum.models import Topic

from .context import EvaluationContext
from .models import MetricValue
from .registry import definition


def _mv(
    metric_id: str,
    value: float | int | str | bool | None,
    *,
    level: str = "run",
    chapter_id: str | None = None,
    topic_id: str | None = None,
    score_0_100: float | None = None,
) -> MetricValue:
    d = definition(metric_id)
    return MetricValue(
        metric_id=metric_id,
        name=d.name,
        dimension=d.dimension,
        value=value,
        unit=d.unit,
        level=level,
        chapter_id=chapter_id,
        topic_id=topic_id,
        score_0_100=score_0_100,
    )


def _pct(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 100.0
    return round(100.0 * numerator / denominator, 2)


def _score_from_rate(rate_pct: float, *, higher_is_better: bool) -> float:
    if higher_is_better:
        return round(rate_pct, 2)
    return round(100.0 - rate_pct, 2)


def _score_from_count(count: int, *, max_ok: int = 0) -> float:
    if count <= max_ok:
        return 100.0
    return max(0.0, round(100.0 - (count - max_ok) * 25.0, 2))


def _detect_prereq_cycles(topics: list[Topic]) -> int:
    graph = {t.topic_id: list(t.prereq_topic_ids) for t in topics}
    visited: set[str] = set()
    stack: set[str] = set()
    cycles = 0

    def dfs(node: str) -> None:
        nonlocal cycles
        if node in stack:
            cycles += 1
            return
        if node in visited:
            return
        visited.add(node)
        stack.add(node)
        for nxt in graph.get(node, []):
            if nxt in graph:
                dfs(nxt)
        stack.remove(node)

    for topic_id in graph:
        dfs(topic_id)
    return cycles


def _hook_uses_forbidden_opener(text: str) -> bool:
    lower = text.strip().lower()
    return any(lower.startswith(opener) for opener in _FORBIDDEN_HOOK_OPENERS)


def _question_payoff_distance(plan: LessonPlan) -> int | None:
    q_idx = next(
        (i for i, s in enumerate(plan.choreography) if s.is_question),
        None,
    )
    p_idx = next(
        (i for i, s in enumerate(plan.choreography) if s.is_payoff),
        None,
    )
    if q_idx is None or p_idx is None:
        return None
    return abs(p_idx - q_idx)


def _crucial_facts_pressed_twice(plan: LessonPlan) -> bool:
    expected = 2 * len(plan.crucial_facts)
    actual = sum(1 for s in plan.choreography if s.presses_crucial_fact)
    return actual >= expected


def _sentence_redundancy_rate(text: str) -> float:
    normalized = re.sub(r"\s+", " ", _strip_markers(text).strip().lower())
    sentences = [
        s.strip()
        for s in re.split(r"[.!?]+", normalized)
        if s.strip() and len(s.strip()) > 20
    ]
    if len(sentences) < 2:
        return 0.0
    counts = Counter(sentences)
    dupes = sum(c - 1 for c in counts.values() if c > 1)
    return round(100.0 * dupes / len(sentences), 2)


def _narration_text_units(ctx: EvaluationContext) -> list[str]:
    units: list[str] = []
    for chapter in ctx.chapters:
        if chapter.narration_text:
            units.append(_strip_markers(chapter.narration_text))
        for narration in chapter.lesson_narrations:
            if narration.full_text_with_markers:
                units.append(_strip_markers(narration.full_text_with_markers))
        script = chapter.assembled_chapter_script or {}
        for segment in script.get("segments", []):
            for key in ("narration_chapter", "narration_standalone"):
                if segment.get(key):
                    units.append(_strip_markers(segment[key]))
    return [u for u in units if u.strip()]


def _strip_markers(text: str) -> str:
    return re.sub(r"<<[^>]+>>", "", text)


def _all_lesson_plans(ctx: EvaluationContext) -> list[LessonPlan]:
    plans: list[LessonPlan] = []
    for chapter in ctx.chapters:
        plans.extend(chapter.lesson_plans)
    return plans


def collect_provenance(ctx: EvaluationContext) -> list[MetricValue]:
    ext = ctx.extraction
    run = ctx.run
    skipped = len(run.skipped_phases)
    return [
        _mv("P-03", ext.source.extractor_model),
        _mv("P-09", ext.textbook_title),
        _mv("P-10", ext.subject),
        _mv("P-11", len(ctx.chapters)),
        _mv("P-13", skipped, score_0_100=_score_from_count(skipped)),
        _mv(
            "P-14",
            run.total_elapsed_seconds,
            score_0_100=None,
        ),
    ]


def collect_curriculum(ctx: EvaluationContext) -> list[MetricValue]:
    topics = ctx.topics
    topic_ids = ctx.topic_ids
    n_topics = len(topics)

    id_counts = Counter(t.topic_id for t in topics)
    duplicate_ids = sum(c - 1 for c in id_counts.values() if c > 1)

    dangling = 0
    for topic in topics:
        for prereq in topic.prereq_topic_ids:
            if prereq not in topic_ids:
                dangling += 1

    empty_understanding = sum(1 for t in topics if not t.our_understanding.strip())
    needs_review = sum(1 for t in topics if t.needs_review)
    embedded = sum(1 for t in topics if t.embedding)

    total_prereq_links = sum(len(t.prereq_topic_ids) for t in topics)
    total_book_examples = sum(len(t.book_examples) for t in topics)
    orig_chars = sum(len(t.orig_book_content) for t in topics)
    understanding_chars = sum(len(t.our_understanding) for t in topics)

    cycles = _detect_prereq_cycles(topics)
    review_rate = _pct(needs_review, n_topics)
    embed_rate = _pct(embedded, n_topics)

    return [
        _mv("CE-01", n_topics),
        _mv("CE-02", len(ctx.extraction.diagrams)),
        _mv("CE-03", len(ctx.extraction.questions)),
        _mv(
            "CE-05",
            duplicate_ids,
            score_0_100=_score_from_count(duplicate_ids),
        ),
        _mv(
            "CE-06",
            dangling,
            score_0_100=_score_from_count(dangling),
        ),
        _mv(
            "CE-07",
            cycles,
            score_0_100=_score_from_count(cycles),
        ),
        _mv(
            "CE-08",
            empty_understanding,
            score_0_100=_score_from_rate(
                _pct(empty_understanding, n_topics), higher_is_better=False
            ),
        ),
        _mv(
            "CE-12",
            review_rate,
            score_0_100=_score_from_rate(review_rate, higher_is_better=False),
        ),
        _mv(
            "CE-15",
            embed_rate,
            score_0_100=_score_from_rate(embed_rate, higher_is_better=True),
        ),
        _mv(
            "CE-16",
            round(total_prereq_links / n_topics, 3) if n_topics else 0.0,
        ),
        _mv(
            "CE-17",
            round(total_book_examples / n_topics, 3) if n_topics else 0.0,
        ),
        _mv("CE-18", orig_chars),
        _mv("CE-19", understanding_chars),
    ]


def collect_chapter_arc(ctx: EvaluationContext) -> list[MetricValue]:
    metrics: list[MetricValue] = []
    for chapter in ctx.chapters:
        seq_len = len(chapter.topic_ids)
        has_plan = chapter.lecture_plan is not None
        planned_topics = len(chapter.topic_ids)
        lesson_plan_topics = len(chapter.lesson_plans)
        coverage = (
            round(lesson_plan_topics / planned_topics, 3) if planned_topics else 0.0
        )
        metrics.extend(
            [
                _mv(
                    "CA-01",
                    seq_len,
                    level="chapter",
                    chapter_id=chapter.chapter_id,
                ),
                _mv(
                    "CA-03",
                    has_plan,
                    level="chapter",
                    chapter_id=chapter.chapter_id,
                    score_0_100=100.0 if has_plan else 0.0,
                ),
                _mv(
                    "CA-05",
                    coverage,
                    level="chapter",
                    chapter_id=chapter.chapter_id,
                    score_0_100=round(coverage * 100.0, 2),
                ),
            ]
        )

    if not ctx.chapters:
        return metrics

    avg_seq = round(
        sum(len(c.topic_ids) for c in ctx.chapters) / len(ctx.chapters), 2
    )
    plan_rate = _pct(
        sum(1 for c in ctx.chapters if c.lecture_plan is not None),
        len(ctx.chapters),
    )
    avg_coverage = round(
        sum(
            (len(c.lesson_plans) / len(c.topic_ids)) if c.topic_ids else 0.0
            for c in ctx.chapters
        )
        / len(ctx.chapters),
        3,
    )
    metrics.extend(
        [
            _mv("CA-01", avg_seq),
            _mv(
                "CA-03",
                plan_rate == 100.0,
                score_0_100=plan_rate,
            ),
            _mv(
                "CA-05",
                avg_coverage,
                score_0_100=round(avg_coverage * 100.0, 2),
            ),
        ]
    )
    return metrics


def collect_lesson_plans(ctx: EvaluationContext) -> list[MetricValue]:
    plans = _all_lesson_plans(ctx)
    n_topics = len(ctx.topics)
    if not plans:
        return [
            _mv("LP-01", 0.0, score_0_100=0.0),
        ]

    forbidden_hooks = sum(
        1 for p in plans if _hook_uses_forbidden_opener(p.hook.text)
    )
    pressed_twice = sum(1 for p in plans if _crucial_facts_pressed_twice(p))
    qp_pairs = sum(
        1
        for p in plans
        if any(s.is_question for s in p.choreography)
        and any(s.is_payoff for s in p.choreography)
    )
    over_cap = sum(1 for p in plans if len(p.diagrams) > 2)

    distances = [d for p in plans if (d := _question_payoff_distance(p)) is not None]
    avg_distance = round(sum(distances) / len(distances), 2) if distances else 0.0

    total_equations = sum(len(p.equations) for p in plans)
    motivated = sum(
        1
        for p in plans
        for eq in p.equations
        if eq.explanation_in_words.strip()
    )
    build_ups = sum(
        1 for p in plans for d in p.diagrams if d.presentation_mode == "build_up"
    )

    plan_rate = _pct(len(plans), n_topics)
    pressed_rate = _pct(pressed_twice, len(plans))
    qp_rate = _pct(qp_pairs, len(plans))
    eq_motivation_rate = _pct(motivated, total_equations) if total_equations else 100.0

    return [
        _mv("LP-01", plan_rate, score_0_100=plan_rate),
        _mv(
            "LP-02",
            forbidden_hooks,
            score_0_100=_score_from_count(forbidden_hooks),
        ),
        _mv(
            "LP-04",
            round(sum(len(p.hook.text) for p in plans) / len(plans), 1),
        ),
        _mv(
            "LP-06",
            round(sum(len(p.crucial_facts) for p in plans) / len(plans), 2),
        ),
        _mv("LP-08", pressed_rate, score_0_100=pressed_rate),
        _mv(
            "LP-09",
            round(sum(len(p.diagrams) for p in plans) / len(plans), 2),
        ),
        _mv(
            "LP-10",
            over_cap,
            score_0_100=_score_from_count(over_cap),
        ),
        _mv(
            "LP-13",
            round(sum(len(p.choreography) for p in plans) / len(plans), 1),
        ),
        _mv("LP-16", qp_rate, score_0_100=qp_rate),
        _mv("LP-17", avg_distance),
        _mv("LP-20", total_equations),
        _mv("LP-21", eq_motivation_rate, score_0_100=eq_motivation_rate),
        _mv("LP-22", build_ups),
    ]


def collect_narration(ctx: EvaluationContext) -> list[MetricValue]:
    units = _narration_text_units(ctx)
    if not units:
        return [
            _mv("NR-48", 0.0, score_0_100=100.0),
            _mv("NR-49", 0.0),
        ]

    redundancy_rates = [_sentence_redundancy_rate(u) for u in units]
    redundancy = round(sum(redundancy_rates) / len(redundancy_rates), 2)
    words = sum(len(u.split()) for u in units)
    topic_count = max(len(ctx.topics), 1)

    return [
        _mv(
            "NR-48",
            redundancy,
            score_0_100=_score_from_rate(redundancy, higher_is_better=False),
        ),
        _mv("NR-49", round(words / topic_count, 1)),
    ]


def collect_layout(ctx: EvaluationContext) -> list[MetricValue]:
    fills: list[float] = []
    for chapter in ctx.chapters:
        for page in chapter.pages:
            if page.notebook_height_total_px > 0:
                fills.append(
                    100.0
                    * page.notebook_height_used_px
                    / page.notebook_height_total_px
                )
    if not fills:
        return []
    avg_fill = round(sum(fills) / len(fills), 2)
    return [
        _mv("LY-14", avg_fill, score_0_100=avg_fill),
    ]


def collect_educational(ctx: EvaluationContext) -> list[MetricValue]:
    plans = _all_lesson_plans(ctx)
    question_steps = sum(
        sum(1 for s in p.choreography if s.is_question) for p in plans
    )
    payoff_steps = sum(
        sum(1 for s in p.choreography if s.is_payoff) for p in plans
    )
    reinforcements = sum(
        sum(1 for s in p.choreography if s.presses_crucial_fact) for p in plans
    )

    units = _narration_text_units(ctx)
    repetition = (
        round(sum(_sentence_redundancy_rate(u) for u in units) / len(units), 2)
        if units
        else 0.0
    )

    assembled_count = sum(
        1 for c in ctx.chapters if c.assembled_chapter_script is not None
    )
    has_assembled = assembled_count == len(ctx.chapters) and bool(ctx.chapters)

    n_plans = len(plans) or 1
    return [
        _mv(
            "EDU-20",
            repetition,
            score_0_100=_score_from_rate(repetition, higher_is_better=False),
        ),
        _mv("EDU-51", round(question_steps / n_plans, 2)),
        _mv("EDU-52", round(payoff_steps / n_plans, 2)),
        _mv("EDU-60", reinforcements),
        _mv(
            "EDU-62",
            has_assembled,
            score_0_100=100.0 if has_assembled else 0.0,
        ),
    ]


def collect_snapshot(ctx: EvaluationContext) -> list[MetricValue]:
    snap = ctx.quality_snapshot
    if snap is None:
        return []

    metrics: list[MetricValue] = []

    if snap.validation:
        v = snap.validation
        checked = max(v.semantic_topics_checked, 1)
        flagged_rate = round(100.0 * v.semantic_topics_flagged / checked, 2)
        render_checked = max(v.diagram_render_checked, 1)
        render_fail_rate = round(
            100.0 * v.diagram_render_failed / render_checked, 2
        )
        metrics.extend(
            [
                _mv(
                    "CE-09",
                    flagged_rate,
                    score_0_100=_score_from_rate(
                        flagged_rate, higher_is_better=False
                    ),
                ),
                _mv(
                    "CE-13",
                    render_fail_rate,
                    score_0_100=_score_from_rate(
                        render_fail_rate, higher_is_better=False
                    ),
                ),
                _mv(
                    "CE-14",
                    v.semantic_wrong_count,
                    score_0_100=_score_from_count(v.semantic_wrong_count),
                ),
            ]
        )

    plan_scores: list[int] = []
    plan_passed = 0
    plan_total = 0
    regen_attempts: list[int] = []
    diagram_scores: list[int] = []
    diagram_passed = 0
    diagram_total = 0

    for chapter in snap.chapters:
        for topic_gate in chapter.topic_gates:
            if topic_gate.plan_judgement is not None:
                plan_total += 1
                plan_scores.append(topic_gate.plan_judgement.score)
                if topic_gate.plan_judgement.passed:
                    plan_passed += 1
            regen_attempts.append(topic_gate.plan_regen_attempts)
            for diagram in topic_gate.diagram_judgements:
                diagram_total += 1
                diagram_scores.append(diagram.score)
                if diagram.passed:
                    diagram_passed += 1

    if plan_total:
        avg_plan = round(sum(plan_scores) / plan_total, 2)
        plan_pass_rate = _pct(plan_passed, plan_total)
        metrics.extend(
            [
                _mv(
                    "LP-30",
                    avg_plan,
                    score_0_100=round(avg_plan / 5.0 * 100.0, 2),
                ),
                _mv("LP-31", plan_pass_rate, score_0_100=plan_pass_rate),
            ]
        )
    if regen_attempts:
        avg_regen = round(sum(regen_attempts) / len(regen_attempts), 2)
        metrics.append(
            _mv(
                "LP-32",
                avg_regen,
                score_0_100=_score_from_rate(avg_regen, higher_is_better=False),
            )
        )

    if diagram_total:
        avg_diagram = round(sum(diagram_scores) / diagram_total, 2)
        diagram_pass_rate = _pct(diagram_passed, diagram_total)
        metrics.extend(
            [
                _mv(
                    "DG-34",
                    avg_diagram,
                    score_0_100=round(avg_diagram / 5.0 * 100.0, 2),
                ),
                _mv("DG-35", diagram_pass_rate, score_0_100=diagram_pass_rate),
            ]
        )

    coverages = [
        ch.book_coverage_pct
        for ch in snap.chapters
        if ch.book_coverage_pct is not None
    ]
    total_gaps = sum(ch.book_coverage_gaps for ch in snap.chapters)
    if coverages:
        avg_coverage = round(sum(coverages) / len(coverages), 2)
        metrics.extend(
            [
                _mv("BE-01", avg_coverage, score_0_100=avg_coverage),
                _mv(
                    "BE-02",
                    total_gaps,
                    score_0_100=_score_from_count(total_gaps),
                ),
            ]
        )

    judgements = ctx.narration_judgements or snap.narration_judgements
    active = [j for j in judgements if not j.skipped]
    if active:
        avg_domain = round(
            sum(j.domain_fit_score for j in active) / len(active), 2
        )
        avg_leakage = round(
            sum(j.analogy_leakage_score for j in active) / len(active), 2
        )
        leakage_score = round(100.0 - avg_leakage, 2)
        avg_clarity = round(sum(j.clarity_score for j in active) / len(active), 2)
        avg_engagement = round(
            sum(j.engagement_score for j in active) / len(active), 2
        )
        avg_factual = round(
            sum(j.factual_grounding_score for j in active) / len(active), 2
        )
        metrics.extend(
            [
                _mv("EDU-domain-fit", avg_domain, score_0_100=avg_domain),
                _mv(
                    "EDU-analogy-leakage",
                    avg_leakage,
                    score_0_100=leakage_score,
                ),
                _mv("NR-clarity", avg_clarity, score_0_100=avg_clarity),
                _mv("NR-engagement", avg_engagement, score_0_100=avg_engagement),
                _mv(
                    "EDU-factual-grounding",
                    avg_factual,
                    score_0_100=avg_factual,
                ),
            ]
        )

    return metrics


def collect_cost(
    ctx: EvaluationContext, *, les: float | None
) -> list[MetricValue]:
    elapsed = ctx.run.total_elapsed_seconds
    if elapsed is None or les is None or elapsed <= 0:
        return []
    minutes = elapsed / 60.0
    qpm = round(les / minutes, 2)
    return [_mv("CO-10", qpm)]


def collect_all(ctx: EvaluationContext) -> list[MetricValue]:
    metrics: list[MetricValue] = []
    metrics.extend(collect_provenance(ctx))
    metrics.extend(collect_curriculum(ctx))
    metrics.extend(collect_chapter_arc(ctx))
    metrics.extend(collect_lesson_plans(ctx))
    metrics.extend(collect_narration(ctx))
    metrics.extend(collect_layout(ctx))
    metrics.extend(collect_educational(ctx))
    metrics.extend(collect_snapshot(ctx))
    return metrics
