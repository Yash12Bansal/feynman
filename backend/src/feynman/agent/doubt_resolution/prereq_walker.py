"""Prereq-walk doubt router (Idea 3).

When a doubt arrives on topic X, the resolution planner today builds its
prompt from `ChapterContext.topic + adjacent_topics`. That gives the LLM a
window over the *lesson order*, not the *concept dependency graph*. Two
problems:

  1. The lesson order is usually correct but not always — `prereq_topic_ids`
     can point to any earlier topic (or none) regardless of section number.
  2. When a student is genuinely stuck because they missed a prerequisite,
     "the topic just before this one" is exactly the wrong place to look —
     the prereq might be three sections earlier.

This walker does a deterministic BFS over `TopicMeta.prereq_topic_ids`
from the doubt's current topic, returning topics in dependency order. The
planner injects the resulting chain into its prompt as "PREREQ CHAIN" — the
LLM keeps authoring the plan but with real curriculum-graph data instead of
hand-rolled section-number heuristics.

Pure function, no IO. Tested directly against an in-memory ChapterContext.
"""

from __future__ import annotations

from collections import deque

from feynman.agent.doubt_resolution.models import ChapterContext, TopicMeta

# Reasonable upper bound; in practice a chapter's curriculum graph is shallow
# (rarely more than 2-3 hops). Cap protects against accidental cycles in
# LLM-derived prereq edges (the extraction pipeline doesn't enforce DAG-ness).
_MAX_DEPTH = 3


def walk_prereqs(
    chapter_context: ChapterContext,
    current_topic_id: str | None,
    *,
    max_depth: int = _MAX_DEPTH,
) -> list[TopicMeta]:
    """Return prereq topics reachable from `current_topic_id` in BFS order.

    `current_topic_id` itself is excluded. Topics with no prereqs return [].
    Cycles are tolerated (visited-set prevents re-traversal); duplicates from
    multiple paths return only once at the first depth they appear.
    """
    if not current_topic_id:
        return []
    start = chapter_context.topics.get(current_topic_id)
    if start is None:
        return []

    visited: set[str] = {current_topic_id}
    queue: deque[tuple[str, int]] = deque(
        (pid, 1) for pid in start.prereq_topic_ids
    )
    chain: list[TopicMeta] = []

    while queue:
        topic_id, depth = queue.popleft()
        if topic_id in visited or depth > max_depth:
            continue
        visited.add(topic_id)
        meta = chapter_context.topics.get(topic_id)
        if meta is None:
            # Edge points to a topic from a different chapter — skip silently.
            continue
        chain.append(meta)
        for next_pid in meta.prereq_topic_ids:
            if next_pid not in visited:
                queue.append((next_pid, depth + 1))

    return chain
