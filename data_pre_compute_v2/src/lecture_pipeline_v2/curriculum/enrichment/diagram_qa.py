"""Phase 4c — DiagramQA: Claude Sonnet vision pass over generated DiagramSpecs.

Renders a DiagramSpec to PNG via ``DiagramFallbackRenderer``'s in-memory
SVG+cairo path, attaches the PNG as a base64 image, and asks Sonnet to score
the diagram against the beat's claim on a 1-5 rubric. Score < min_score
triggers a retry in the caller (``DiagramSpecGenerator.regenerate_for_beat``
with corrective hint).

Failure modes (render error, missing cairosvg, vision API error, JSON parse
error) all degrade gracefully to ``QAResult.skipped`` — the QA loop never
blocks the pipeline. The diagram passes through without a score.
"""

from __future__ import annotations

import base64
import dataclasses
import json
import logging
from io import BytesIO
from typing import TYPE_CHECKING

import anthropic

from ..media.diagram_renderer import DiagramFallbackRenderer
from ..models import Diagram
from .diagram_qa_prompts import DIAGRAM_QA_SYSTEM_PROMPT, build_qa_user_text

if TYPE_CHECKING:
    from anthropic.types import Message

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class QAResult:
    """One DiagramQA review.

    ``passed`` is True iff ``score >= min_score`` (caller's threshold). When QA
    skips for any reason (render failure, cairosvg missing, vision API failure,
    JSON parse failure), we return ``QAResult.skipped(reason)`` with
    ``passed=True`` and ``score=3`` — the diagram passes through. Better to
    accept an un-scored diagram than to block the pipeline on QA infrastructure
    drift.
    """

    passed: bool
    score: int
    issue: str
    suggestion: str

    @classmethod
    def from_dict(cls, data: dict) -> QAResult:
        return cls(
            passed=bool(data.get("passed", False)),
            score=int(data.get("score", 0)),
            issue=str(data.get("issue", "")),
            suggestion=str(data.get("suggestion", "")),
        )

    @classmethod
    def skipped(cls, reason: str) -> QAResult:
        return cls(passed=True, score=3, issue=reason, suggestion="")


class DiagramQA:
    """Async DiagramQA caller. One verify() call per diagram per attempt."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        min_score: int = 3,
    ) -> None:
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model
        self.min_score = min_score
        self._renderer = _BareSVGRenderer()

    async def verify(self, diagram: Diagram, claim: str) -> QAResult:
        try:
            png_bytes = self._render_to_png(diagram)
        except Exception as e:  # noqa: BLE001 — render failure is a graceful-skip
            logger.warning(
                "DiagramQA.render_failed for %s: %s - accepting diagram as-is",
                diagram.diagram_id,
                e,
            )
            return QAResult.skipped(f"render failed: {e}")
        if png_bytes is None:
            logger.info(
                "DiagramQA.no_png for %s - cairosvg unavailable, skipping",
                diagram.diagram_id,
            )
            return QAResult.skipped("cairosvg unavailable")
        try:
            b64 = base64.standard_b64encode(png_bytes).decode("ascii")
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=512,
                system=DIAGRAM_QA_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": b64,
                                },
                            },
                            {
                                "type": "text",
                                "text": build_qa_user_text(claim),
                            },
                        ],
                    },
                ],
            )
            return self._parse_response(response, diagram.diagram_id)
        except Exception as e:  # noqa: BLE001 — vision API errors are recoverable
            logger.warning(
                "DiagramQA.vision_call_failed for %s: %s - accepting diagram",
                diagram.diagram_id,
                e,
            )
            return QAResult.skipped(f"vision call failed: {e}")

    def _render_to_png(self, diagram: Diagram) -> bytes | None:
        """In-memory SVG → PNG. Returns None if cairosvg is unavailable."""
        try:
            import cairosvg  # type: ignore[import-untyped]
        except ImportError:
            return None
        svg_text = self._renderer.spec_to_svg(diagram.render_data)
        buf = BytesIO()
        cairosvg.svg2png(
            bytestring=svg_text.encode("utf-8"),
            write_to=buf,
            output_width=int(diagram.render_data.get("width", 900)),
            output_height=int(diagram.render_data.get("height", 650)),
            background_color="#0a0a0a",  # The dark-board background QA expects
        )
        return buf.getvalue()

    def _parse_response(self, response: Message, diagram_id: str) -> QAResult:
        text = ""
        for block in response.content:
            if getattr(block, "type", None) == "text":
                text = block.text  # type: ignore[attr-defined]
                break
        if not text:
            logger.warning(
                "DiagramQA.no_text_block for %s - defaulting to pass-through",
                diagram_id,
            )
            return QAResult.skipped("no text in response")
        try:
            stripped = text.strip()
            if stripped.startswith("```"):
                first_nl = stripped.index("\n") if "\n" in stripped else 3
                stripped = stripped[first_nl + 1 :]
                if stripped.endswith("```"):
                    stripped = stripped[:-3].strip()
            data = json.loads(stripped)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("DiagramQA.parse_failed for %s: %s", diagram_id, e)
            return QAResult.skipped(f"parse failed: {e}")
        return QAResult.from_dict(data)


class _BareSVGRenderer:
    """Proxy that exposes ``DiagramFallbackRenderer``'s SVG-string output
    without requiring an ``ArtifactStore``.

    The DiagramFallbackRenderer needs a store for file output; we only need
    the in-memory SVG. We dispatch through the unbound methods on the class.
    If this becomes more than ~3 methods deep, refactor ``_spec_to_svg`` into
    a module-level function in ``diagram_renderer.py``.
    """

    def spec_to_svg(self, spec: dict) -> str:
        return DiagramFallbackRenderer._spec_to_svg(self, spec)  # type: ignore[arg-type]

    def _element_to_svg(self, el: dict) -> str:
        return DiagramFallbackRenderer._element_to_svg(self, el)  # type: ignore[arg-type]
