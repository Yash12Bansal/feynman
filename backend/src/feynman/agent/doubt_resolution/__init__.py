"""Doubt-resolution pipeline.

When a student taps Ask Feynman during a precomputed lecture, this package
classifies their doubt, plans a resolution (with optional precomputed-
diagram reuse), and hands the plan to Phase 5 for live voice + visual
delivery.

Public surface:
- `LectureDoubtSession` — per-session coordinator (owns ChapterContext +
  prior-doubts history + shown-diagram set).
- `classify_doubt` / `plan_resolution` / `match_diagrams_for_plan` —
  the three stages, callable directly for tests.
- `load_chapter_by_id` — hydrate a ChapterContext from Neo4j (or
  `chapter_context_from_extraction` for hermetic tests).
- `DoubtClassification`, `DoubtType`, `ResolutionPlan`, `ResolutionBeat`,
  `ChapterContext` — the data shapes Phase 5 will consume.
"""

from feynman.agent.doubt_resolution.chapter_loader import (
    chapter_context_from_extraction,
    load_chapter_by_id,
)
from feynman.agent.doubt_resolution.diagram_fit_matcher import (
    match_diagrams_for_plan,
)
from feynman.agent.doubt_resolution.doubt_classifier import (
    DoubtClassification,
    DoubtType,
    classify_doubt,
)
from feynman.agent.doubt_resolution.lecture_session import LectureDoubtSession
from feynman.agent.doubt_resolution.models import (
    AnnotationAction,
    ChapterContext,
    DiagramData,
    DoubtRecord,
    FitVerdict,
    FocusAction,
    MarkPointAction,
    PointAtAction,
    ResolutionBeat,
    ResolutionPlan,
    TopicMeta,
    TraceAction,
)
from feynman.agent.doubt_resolution.resolution_planner import plan_resolution

__all__ = [
    "AnnotationAction",
    "ChapterContext",
    "DiagramData",
    "DoubtClassification",
    "DoubtRecord",
    "DoubtType",
    "FitVerdict",
    "FocusAction",
    "LectureDoubtSession",
    "MarkPointAction",
    "PointAtAction",
    "ResolutionBeat",
    "ResolutionPlan",
    "TopicMeta",
    "TraceAction",
    "chapter_context_from_extraction",
    "classify_doubt",
    "load_chapter_by_id",
    "match_diagrams_for_plan",
    "plan_resolution",
]
