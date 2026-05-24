"""Manifest composer — annotation + layout policies on the chunker fragment stream.

Phase 2: dynamic board referencing. Walker validates annotations against
the active diagram's `dictionary`, enforces one-shot/cooldown/rate/budget/
spatial rules.

Phase 3: layout + pagination intelligence. When constructed with a
LayoutConfig + MeasurementService, the same walker measures every notebook
block, stamps `placement` onto fragments, and injects PageBreakFragments
at overflow / diagram-change / writer-marker triggers.

Public surface:
    ManifestComposer       — the entry point
    Walker                 — the per-fragment state machine
    ComposerReport         — emit/drop/page counters
    MeasurementService     — Phase 3 Playwright measurement + cache
    LayoutPlanner          — Phase 3 page-state model + slide-action resolver
"""

from .composer import ManifestComposer
from .measurement import MeasurementService
from .policies.layout import LayoutPlanner, PageState, SlideState, NotebookState
from .walker import ComposerReport, Walker

__all__ = [
    "ComposerReport",
    "LayoutPlanner",
    "ManifestComposer",
    "MeasurementService",
    "NotebookState",
    "PageState",
    "SlideState",
    "Walker",
]
