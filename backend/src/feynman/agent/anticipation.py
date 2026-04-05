"""Anticipation engine — pre-generates design diagrams before the teacher needs them.

Supports two curriculum sources:
- ConceptGraph (from data_pre_compute): richer prompts from exhaustive node summaries
- LessonPlan: fallback using visual_suggestions

The engine fires at session start (first N concepts) and on each concept advance
(next N concepts). When draw_design_diagram is called, it checks the cache first —
cache hit = 0ms instead of 5-15s.
"""

from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from feynman.agent.lesson_plan import ConceptNode as LessonConceptNode
    from feynman.agent.lesson_plan import LessonPlan
    from feynman.agent.session_audit import SessionAudit

logger = structlog.get_logger()

# ── Classification keywords ───────────────────────────────

# Suggestions/summaries matching these need the design agent (spatial diagrams).
_DESIGN_KEYWORDS = re.compile(
    r"\b(diagram|draw\w*|illustrat\w*|show\s+setup|apparatus|figure|schematic|"
    r"sketch\w*|depict\w*|visual(?:ize|ise)\w*|layout|cross[- ]section|ray\s+diagram|"
    r"circuit|free\s+body|arrangement|setup)\b",
    re.IGNORECASE,
)

# These are handled by fast tools (show_equation, show_graph, step_equation, draw_diagram).
_FAST_TOOL_KEYWORDS = re.compile(
    r"\b(equation\w*|formula\w*|graph\w*|plot\w*|chart\w*|deriv\w+|proof|prove\w*|"
    r"simplif\w*|substitut\w*|calculat\w*|table|flowchart|concept\s+map)\b",
    re.IGNORECASE,
)


def _needs_design_agent(text: str) -> bool:
    """Classify whether a text description needs the design agent.

    Returns True if the content describes a spatial diagram that requires
    the design agent's SVG generation. Returns False for content that
    fast tools handle (equations, graphs, flowcharts).

    When both keyword sets match, fast-tool wins because fast-tool keywords
    name specific content types (flowchart, graph, equation) while design
    keywords are generic actions (draw, diagram, illustrate).
    Exception: compound design phrases like "ray diagram", "free body",
    "circuit", "apparatus" are specific enough to override.
    """
    has_fast = bool(_FAST_TOOL_KEYWORDS.search(text))
    has_design = bool(_DESIGN_KEYWORDS.search(text))

    # Fast-tool keywords name specific handled content types — they take priority.
    if has_fast:
        # Compound design phrases override fast keywords (e.g. "ray diagram").
        return bool(_COMPOUND_DESIGN_RE.search(text))
    return has_design


# Compound phrases that are specifically design-agent territory regardless of
# other keywords. These describe actual spatial/physical visuals, not abstract
# content types like "flowchart" or "graph".
_COMPOUND_DESIGN_RE = re.compile(
    r"\b(ray\s+diagram|free\s+body|circuit\s+diagram|apparatus|schematic|"
    r"cross[- ]section|experimental\s+setup|anatomical|"
    r"lens\s+diagram|mirror\s+diagram)\b",
    re.IGNORECASE,
)


# ── Keyword matching ──────────────────────────────────────

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    """Extract lowercase alphanumeric tokens from text."""
    return set(_WORD_RE.findall(text.lower()))


# Common words that add noise to matching — skip them.
_STOP_WORDS = frozenset({
    "the", "a", "an", "of", "in", "on", "for", "to", "and", "with", "is",
    "are", "was", "were", "be", "been", "being", "that", "this", "it",
    "from", "by", "at", "or", "as", "use", "show", "draw", "using",
    "how", "what", "when", "where", "which", "should", "would", "could",
})


def _meaningful_tokens(text: str) -> set[str]:
    """Tokenize and remove stop words."""
    return _tokenize(text) - _STOP_WORDS


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two token sets."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ── Graph prompt extraction ──────────────────────────────

def _build_prompt_from_graph_node(
    node: Any,  # data_pre_compute ConceptNode
    graph: Any,  # data_pre_compute ConceptGraph
) -> str | None:
    """Extract a design diagram prompt from a ConceptGraph node's summary.

    Returns None only if the node has no summary at all. Every ConceptGraph
    node with content is worth pre-generating a visual for — the design agent
    can always create a useful teaching diagram from rich curriculum text,
    even for equation-heavy topics (it draws annotated equation breakdowns,
    variable relationship diagrams, etc.).
    """
    summary = node.summary or ""
    topic = node.topic_name or ""

    if not summary:
        return None

    # Build a rich prompt from the node's exhaustive summary.
    parts = [f"Draw a detailed educational diagram for: {topic}."]

    if summary:
        # Include relevant visual context from the summary (truncated to keep
        # the prompt focused — Claude works better with specific instructions).
        parts.append(f"Context: {summary[:600]}")

    # Add prerequisite context from edges — what students already understand.
    try:
        edges = graph.get_related_edges(node.node_id)
        prereqs = [
            e for e in edges
            if e.relation.value == "prerequisite" and e.target_id == node.node_id
        ]
        if prereqs:
            prereq_names = []
            for e in prereqs[:3]:
                prereq_node = graph.nodes.get(e.source_id)
                if prereq_node:
                    prereq_names.append(prereq_node.topic_name)
            if prereq_names:
                parts.append(
                    f"Students already understand: {', '.join(prereq_names)}."
                )
    except Exception:
        pass  # Edge lookup failure is non-critical

    return " ".join(parts)


def _extract_visual_prompts_from_plan(
    concept: LessonConceptNode,
) -> list[str]:
    """Extract design-agent-worthy prompts from a LessonPlan concept's visual_suggestions."""
    prompts = []
    for suggestion in concept.visual_suggestions:
        if _needs_design_agent(suggestion):
            # Enrich with concept context.
            prompt = (
                f"{suggestion}. "
                f"Topic: {concept.title}. "
                f"Context: {concept.description}"
            )
            prompts.append(prompt)
    return prompts


# ── Main engine ──────────────────────────────────────────


class AnticipationEngine:
    """Pre-generates design diagram specs from curriculum data.

    Cache is keyed by (concept_index, suggestion_index). When draw_design_diagram
    is called, match() checks the cache by keyword overlap with the prompt.
    """

    def __init__(self, audit: SessionAudit | None = None) -> None:
        # (concept_index, suggestion_index) → DiagramSpec dict
        self._cache: dict[tuple[int, int], dict[str, Any]] = {}
        # (concept_index, suggestion_index) → prompt text used for generation
        self._prompts: dict[tuple[int, int], str] = {}
        # Keys currently being generated (to avoid duplicate fire)
        self._generating: set[tuple[int, int]] = set()
        self._audit = audit
        # Doubt branch cache — one-shot, cleared on resolve or first match
        self._doubt_spec: dict[str, Any] | None = None
        self._doubt_prompt: str = ""

    @property
    def cache_size(self) -> int:
        return len(self._cache)

    async def warm(
        self,
        plan: LessonPlan,
        start: int = 0,
        count: int = 3,
        graph: Any | None = None,
    ) -> None:
        """Unified entry point — routes to graph or plan path."""
        if graph:
            await self.warm_from_graph(graph, plan, start, count)
        else:
            await self.warm_from_plan(plan, start, count)

    async def warm_from_graph(
        self,
        graph: Any,  # ConceptGraph
        plan: LessonPlan,
        start: int = 0,
        count: int = 3,
    ) -> None:
        """Pre-generate using ConceptGraph node summaries (preferred path).

        For each concept in range, uses the graph node's exhaustive summary
        to build a rich, specific diagram prompt — dramatically better than
        LessonPlan visual_suggestions.
        """
        if self._audit:
            self._audit.record("anticipation", "source_graph", f"start={start}, count={count}")

        teaching_order = graph.get_teaching_order()
        # Map plan concept indices to graph nodes by matching topic names.
        end = min(start + count, plan.total_concepts)
        tasks: list[tuple[tuple[int, int], str]] = []

        for concept_idx in range(start, end):
            plan_concept = plan.concept_at(concept_idx)
            if not plan_concept:
                continue

            # Find matching graph node by topic name (fuzzy).
            plan_tokens = _meaningful_tokens(plan_concept.title)
            best_node = None
            best_score = 0.0
            for gnode in teaching_order:
                score = _jaccard(plan_tokens, _meaningful_tokens(gnode.topic_name))
                if score > best_score:
                    best_score = score
                    best_node = gnode

            if best_node and best_score > 0.2:
                prompt = _build_prompt_from_graph_node(best_node, graph)
                if prompt:
                    key = (concept_idx, 0)
                    tasks.append((key, prompt))
            else:
                # Fallback to plan-based extraction for this concept.
                for si, prompt in enumerate(
                    _extract_visual_prompts_from_plan(plan_concept)
                ):
                    key = (concept_idx, si)
                    tasks.append((key, prompt))

        await self._generate_batch(tasks)

    async def warm_from_plan(
        self,
        plan: LessonPlan,
        start: int = 0,
        count: int = 3,
    ) -> None:
        """Pre-generate using LessonPlan visual_suggestions (fallback path).

        For each concept in range, classifies each visual_suggestion and
        generates design diagrams for those that need the design agent.
        """
        if self._audit:
            self._audit.record("anticipation", "source_plan", f"start={start}, count={count}")

        end = min(start + count, plan.total_concepts)
        tasks: list[tuple[tuple[int, int], str]] = []

        for concept_idx in range(start, end):
            concept = plan.concept_at(concept_idx)
            if not concept:
                continue
            for si, prompt in enumerate(
                _extract_visual_prompts_from_plan(concept)
            ):
                key = (concept_idx, si)
                tasks.append((key, prompt))

        await self._generate_batch(tasks)

    async def _generate_batch(
        self,
        tasks: list[tuple[tuple[int, int], str]],
    ) -> None:
        """Fire generation for all tasks concurrently, skipping already cached/in-flight."""
        coros = []
        for key, prompt in tasks:
            if key in self._cache or key in self._generating:
                continue
            coros.append(self._generate_one(key, prompt))

        if coros:
            logger.info("anticipation.batch_start", count=len(coros))
            await asyncio.gather(*coros, return_exceptions=True)
            logger.info("anticipation.batch_done", cached=len(self._cache))

    async def _generate_one(
        self,
        key: tuple[int, int],
        prompt: str,
    ) -> None:
        """Generate a single design diagram spec and cache it."""
        self._generating.add(key)
        t0 = time.monotonic()
        try:
            from feynman.agent.design_bridge import generate_design_diagram

            spec = await generate_design_diagram(prompt, model="sonnet")
            self._cache[key] = spec
            self._prompts[key] = prompt

            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.info(
                "anticipation.generated",
                key=key,
                prompt=prompt[:80],
                elapsed_ms=round(elapsed_ms),
                elements=len(spec.get("elements", [])),
            )
            if self._audit:
                self._audit.record(
                    "anticipation",
                    "pre_generated",
                    f"concept={key[0]}, elapsed={elapsed_ms:.0f}ms",
                    concept_index=key[0],
                    elapsed_ms=elapsed_ms,
                )

        except Exception:
            logger.warning(
                "anticipation.generation_failed",
                key=key,
                prompt=prompt[:80],
                exc_info=True,
            )
            if self._audit:
                self._audit.record(
                    "anticipation",
                    "generation_failed",
                    f"concept={key[0]}",
                    concept_index=key[0],
                )
        finally:
            self._generating.discard(key)

    def match(
        self,
        prompt: str,
        concept_index: int,
    ) -> dict[str, Any] | None:
        """Find a cached spec matching the agent's draw_design_diagram prompt.

        Checks doubt cache first (one-shot), then concept_index's cached
        suggestions, then concept_index ± 1 as secondary search.
        Scores by keyword overlap (Jaccard).
        """
        prompt_tokens = _meaningful_tokens(prompt)
        if not prompt_tokens:
            return None

        # Check doubt cache first (one-shot — cleared after match).
        if self._doubt_spec and self._doubt_prompt:
            doubt_tokens = _meaningful_tokens(self._doubt_prompt)
            score = _jaccard(prompt_tokens, doubt_tokens)
            if score >= 0.15:
                logger.info("anticipation.doubt_cache_hit", score=round(score, 3))
                spec = self._doubt_spec
                self._doubt_spec = None
                self._doubt_prompt = ""
                if self._audit:
                    self._audit.record(
                        "doubt",
                        "visual_ready_before_needed",
                        f"score={score:.3f}",
                    )
                return spec

        # Direct concept-index match — cache was built from curriculum for
        # this exact concept, so Jaccard similarity isn't needed.
        direct_keys = [k for k in self._cache if k[0] == concept_index]
        if direct_keys:
            key = min(direct_keys)  # prefer suggestion_index 0
            logger.info(
                "anticipation.concept_index_hit",
                concept=concept_index,
                key=key,
            )
            if self._audit:
                self._audit.record(
                    "anticipation",
                    "concept_index_hit",
                    f"concept={concept_index}, key={key}",
                    concept_index=concept_index,
                )
            return self._cache[key]

        best_score = 0.0
        best_key: tuple[int, int] | None = None

        # Fallback: Jaccard matching for cross-concept (±1) lookups.
        search_indices = [concept_index, concept_index - 1, concept_index + 1]

        for ci in search_indices:
            for key, cached_prompt in self._prompts.items():
                if key[0] != ci:
                    continue
                cached_tokens = _meaningful_tokens(cached_prompt)
                score = _jaccard(prompt_tokens, cached_tokens)
                if score > best_score:
                    best_score = score
                    best_key = key

        # Lower threshold for same concept (agent likely paraphrased the pre-generated prompt)
        # Higher threshold for adjacent concepts (±1 lookahead)
        threshold = 0.15 if (best_key and best_key[0] == concept_index) else 0.3
        if best_key is not None and best_score >= threshold:
            logger.info(
                "anticipation.match_found",
                concept=concept_index,
                matched_key=best_key,
                score=round(best_score, 3),
            )
            return self._cache.get(best_key)

        logger.debug(
            "anticipation.no_match",
            concept=concept_index,
            best_score=round(best_score, 3) if best_score > 0 else 0,
            prompt=prompt[:60],
        )
        return None

    def get_prompts_for_concept(self, concept_index: int) -> list[str]:
        """Return pre-generated diagram prompts for a concept.

        May be empty if the concept hasn't been warmed yet or has no visual content.
        Used by the prompt builder to show the agent what's already cached.
        """
        return [
            prompt
            for (ci, _si), prompt in self._prompts.items()
            if ci == concept_index
        ]

    # ── Doubt branch support ─────────────────────────────────

    async def warm_doubt(
        self,
        concept_desc: str,
        board_summary: str = "",
        parent_concept: str = "",
    ) -> None:
        """Pre-generate a visual for a doubt branch.

        Fired as a background task from start_doubt_branch(). The visual may
        be ready by the time the agent calls draw_design_diagram.
        """
        prompt = f"A student has a doubt about: {concept_desc}"
        if parent_concept:
            prompt += f"\nThis came up while teaching: {parent_concept}"
        if board_summary:
            prompt += f"\nCurrent board shows: {board_summary}"
        prompt += "\nDraw a clear, focused diagram that helps explain this concept."

        self._doubt_prompt = prompt
        if self._audit:
            self._audit.record(
                "doubt", "background_gen_fired", f"concept='{concept_desc[:60]}'"
            )

        t0 = time.monotonic()
        try:
            from feynman.agent.design_bridge import generate_design_diagram

            spec = await generate_design_diagram(prompt, model="sonnet")
            self._doubt_spec = spec
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.info(
                "anticipation.doubt_generated",
                concept=concept_desc[:60],
                elapsed_ms=round(elapsed_ms),
            )
        except Exception:
            self._doubt_spec = None
            logger.warning(
                "anticipation.doubt_generation_failed",
                concept=concept_desc[:60],
                exc_info=True,
            )

    def clear_doubt_cache(self) -> None:
        """Clear doubt-specific cache. Called when resolve_doubt() returns to main lesson."""
        self._doubt_spec = None
        self._doubt_prompt = ""

    def evict_all(self) -> None:
        """Clear the entire anticipation cache. Called on topic switch."""
        count = len(self._cache)
        self._cache.clear()
        self._prompts.clear()
        self._generating.clear()
        self._doubt_spec = None
        self._doubt_prompt = ""
        if count:
            logger.info("anticipation.evicted_all", former_size=count)
        if self._audit:
            self._audit.record(
                "anticipation", "cache_evicted_all", f"cleared {count} entries",
            )

    def evict_before(self, concept_index: int) -> int:
        """Remove cached specs for concepts before the given index.

        Called when advancing concepts — specs for past concepts are unlikely
        to be needed again. Returns number of entries evicted.
        """
        stale_keys = [k for k in self._cache if k[0] < concept_index]
        for key in stale_keys:
            del self._cache[key]
            self._prompts.pop(key, None)
        if stale_keys:
            logger.info(
                "anticipation.evicted",
                count=len(stale_keys),
                before_concept=concept_index,
                cache_size=len(self._cache),
            )
            if self._audit:
                self._audit.record(
                    "anticipation",
                    "cache_evicted",
                    f"evicted={len(stale_keys)}, before_concept={concept_index}",
                    count=len(stale_keys),
                )
        return len(stale_keys)


# ── ConceptGraph loading ──────────────────────────────────

# Default directory where data_pre_compute outputs graph JSON files.
_GRAPH_OUTPUT_DIR = Path(__file__).resolve().parents[4] / "data_pre_compute" / "output" / "graphs"


async def load_concept_graph(
    topic: str,
    graph_dir: Path | None = None,
) -> Any | None:
    """Load a pre-computed ConceptGraph for the given topic.

    Searches the output directory of data_pre_compute for matching graph JSON files.
    Returns None if no graph exists for this topic.
    """
    search_dir = graph_dir or _GRAPH_OUTPUT_DIR
    if not search_dir.exists():
        logger.warning("anticipation.no_graph_dir", path=str(search_dir))
        return None

    # Import ConceptGraph from data_pre_compute (may not be installed).
    try:
        from lecture_pipeline.graph.models import ConceptGraph
    except ImportError:
        logger.warning("anticipation.graph_import_unavailable")
        return None

    topic_tokens = _meaningful_tokens(topic)
    best_graph = None
    best_score = 0.0

    for json_file in search_dir.glob("*.json"):
        try:
            raw = json_file.read_text()
            graph = ConceptGraph.from_json(raw)
            title_tokens = _meaningful_tokens(graph.chapter_title)
            score = _jaccard(topic_tokens, title_tokens)
            if score > best_score:
                best_score = score
                best_graph = graph
        except Exception:
            logger.debug("anticipation.graph_load_error", file=str(json_file), exc_info=True)
            continue

    if best_graph and best_score > 0.2:
        logger.info(
            "anticipation.graph_loaded",
            topic=topic,
            matched_title=best_graph.chapter_title,
            score=round(best_score, 3),
            nodes=len(best_graph.nodes),
        )
        return best_graph

    logger.info("anticipation.no_graph_match", topic=topic, best_score=round(best_score, 3))
    return None
