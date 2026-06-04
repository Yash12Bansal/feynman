"""Public entry point for the manifest composer."""

from __future__ import annotations

import logging
from typing import Any

from ...config import LayoutConfig
from ...tts.chunker import ScriptFragment
from .measurement import MeasurementService
from .policies.layout import LayoutPlanner
from .walker import ComposerReport, Walker

logger = logging.getLogger(__name__)


class ManifestComposer:
    """Applies annotation + layout policies to a chunker fragment stream.

    Construct with a `diagrams_by_id` map so the walker can read each
    diagram's `render_data["dictionary"]` for role validation + bounds.

    Phase 2 contract: fragment-in / fragment-out. The composer drops or
    downgrades annotation fragments that violate policy; it leaves text /
    diagram / notebook fragments untouched. The audio_pipeline still owns
    fragment-to-event emission.

    Phase 3 extension: when `layout_config` and `measurement` are provided,
    the walker also measures every notebook block, stamps placement on
    fragments, and injects synthetic PageBreakFragments at overflow /
    diagram-change / writer-marker boundaries.

    The composer owns a single Walker for its lifetime — calling `compose`
    multiple times advances the same `cumulative_audio_ms` clock, preserves
    per-diagram state across calls, AND keeps `page_state` continuous across
    compose() calls within the chapter. Call `flush()` at chapter end to
    seal the final page summary.
    """

    def __init__(
        self,
        diagrams_by_id: dict[str, Any],
        layout_config: LayoutConfig | None = None,
        measurement: MeasurementService | None = None,
        topic_id: str = "",
    ) -> None:
        layout_planner: LayoutPlanner | None = None
        if layout_config is not None and measurement is not None:
            layout_planner = LayoutPlanner(layout_config, measurement)
        self._walker = Walker(
            diagrams_by_id=diagrams_by_id,
            layout_planner=layout_planner,
            topic_id=topic_id,
        )

    async def compose(self, fragments: list[ScriptFragment]) -> list[ScriptFragment]:
        return await self._walker.walk(fragments)

    def flush(self) -> None:
        """Close any open chapter-level state (e.g., final page summary)."""
        self._walker.flush()

    @property
    def last_report(self) -> ComposerReport:
        """Cumulative report across every compose() call on this composer."""
        return self._walker.report

    @property
    def open_build_up_diagram_id(self) -> str | None:
        """The build_up diagram still on screen at chapter end (or None).

        Read by the audio pipeline after `flush()` to append a reveal-all so a
        lecture never ends on a half-built diagram (Workstream B).
        """
        return self._walker.open_build_up_diagram_id
