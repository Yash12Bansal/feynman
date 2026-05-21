"""Diagram generation — per-topic DiagramSpec creation in svg renderer.

The system prompt is the proven design_agent prompt (carried from v1 verbatim
into this file — we don't import from v1). For each topic we ask the LLM to
produce one or more DiagramSpec JSON objects matching the SVG renderer schema.

Output: Diagram pydantic models. Linked to topics via Diagram.linked_topic_ids
and Topic.has_diagram_ids (the latter wired in the orchestrator).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field

from ...llm.base import LLMProvider
from ..id_generator import generate_diagram_uid
from ..models import Diagram, DiagramRenderer, Topic

logger = logging.getLogger(__name__)


DIAGRAM_SYSTEM_PROMPT = r"""You are an expert teacher who draws clear, beautiful diagrams for students. Every diagram should be something you'd proudly put on a whiteboard or in a textbook. Prioritize clarity over complexity: clean lines, generous spacing, readable labels, logical visual flow. A student seeing your diagram for the first time should immediately understand what's happening.

You output structured JSON diagram specifications. The frontend renders using pure SVG with visx (React). All coordinates are pixel-based (origin top-left, y goes down).

## Output format

Return a single JSON object with this top level:
```
{
  "diagrams": [
    {
      "name": "short identifying name (1-3 words)",
      "description": "1-2 sentence description of what the diagram shows",
      "spec": { "title": "...", "description": "...", "width": 900, "height": 650, "backgroundColor": "#ffffff", "elements": [...], "parameters": [], "animations": [] }
    }
  ]
}
```

Generate 1-3 diagrams per topic. Most topics need only one. Generate more only when the topic clearly has distinct visual aspects.

## Element types

Every element must have a `"type"` field and a unique `"id"`. All coordinate fields accept numbers or expression strings.

### svg_line
`{"type": "svg_line", "id": "...", "x1": 0, "y1": 0, "x2": 100, "y2": 100, "stroke": "#000", "strokeWidth": 2, "strokeDasharray": ""}`

### svg_rect
`{"type": "svg_rect", "id": "...", "x": 0, "y": 0, "width": 100, "height": 50, "fill": "none", "stroke": "#000", "strokeWidth": 2, "rx": 0}`

### svg_circle
`{"type": "svg_circle", "id": "...", "cx": 100, "cy": 100, "r": 50, "stroke": "#000", "fill": "none", "strokeWidth": 2, "strokeDasharray": ""}`

### svg_ellipse
`{"type": "svg_ellipse", "id": "...", "cx": 100, "cy": 100, "rx": 50, "ry": 30, "stroke": "#000", "fill": "none", "strokeWidth": 2}`

### svg_path
`{"type": "svg_path", "id": "...", "d": "M 0 0 L 100 100", "stroke": "#000", "strokeWidth": 2, "fill": "none", "strokeDasharray": ""}`

### svg_text
Plain-text label at a pixel position. NEVER use for math/symbols/equations.
`{"type": "svg_text", "id": "...", "x": 100, "y": 50, "text": "Label", "fontSize": 14, "fill": "#000", "textAnchor": "middle", "fontWeight": "normal"}`

### svg_arc
Circular arc. Angles in degrees, 0 = right (3 o'clock), positive = clockwise.
`{"type": "svg_arc", "id": "...", "cx": 100, "cy": 100, "r": 50, "startAngle": 0, "endAngle": 90, "stroke": "#000", "strokeWidth": 2, "fill": "none"}`

### svg_group
`{"type": "svg_group", "id": "...", "transform": "translate(100, 50)", "elements": [...]}`

### svg_latex
KaTeX math expression. USE THIS for anything with math, symbols, subscripts, superscripts, Greek letters, equations.
`{"type": "svg_latex", "id": "...", "expression": "E = mc^{2}", "x": 100, "y": 50, "fontSize": 16, "color": "#000"}`

### svg_arrow
`{"type": "svg_arrow", "id": "...", "x1": 0, "y1": 0, "x2": 100, "y2": 100, "stroke": "#000", "strokeWidth": 2}`

## Rules

1. Pixel coordinates, origin top-left, y DOWN. Default canvas 900x650. Center ≈ (450, 325).
2. svg_text ONLY for plain-language labels ("Object", "Screen", "Step 1"). svg_latex for ANYTHING with math notation. Write PROPER KaTeX (`\\frac{x^2}{2}`, `\\theta`, `\\int`) — double-escape backslashes in JSON.
3. Use the full canvas. Spread elements out. Keep labels offset from elements they describe.
4. Color coding: barriers #555, waves #4682b4, gravity #4CAF50, tension #FF9800, net force #D32F2F, labels #333.
5. Every element needs a unique id (use the diagram's name as prefix, e.g. "spring_setup_block_1").
6. Return pure JSON only. No markdown fences. No commentary.
"""


@dataclass
class DiagramGenerationReport:
    topics_seen: int = 0
    diagrams_generated: int = 0
    topics_skipped_existing: int = 0
    failures: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    def summary(self) -> str:
        return (
            f"Diagram generation — {self.diagrams_generated} diagrams from "
            f"{self.topics_seen} topics, "
            f"{self.topics_skipped_existing} topics skipped (had diagrams), "
            f"{len(self.failures)} failures, "
            f"{self.elapsed_seconds:.1f}s"
        )


class DiagramGenerator:
    def __init__(self, llm: LLMProvider, *, concurrency: int = 5):
        self.llm = llm
        self.concurrency = concurrency

    async def generate_for_topics(
        self,
        topics: list[Topic],
        existing_diagram_ids: set[str] | None = None,
    ) -> tuple[list[Diagram], DiagramGenerationReport]:
        existing = existing_diagram_ids or set()
        report = DiagramGenerationReport(topics_seen=len(topics))
        start = time.monotonic()

        if not topics:
            report.elapsed_seconds = time.monotonic() - start
            return [], report

        semaphore = asyncio.Semaphore(self.concurrency)
        tasks = [self._generate_for_one(topic, existing, semaphore, report) for topic in topics]
        results = await asyncio.gather(*tasks)

        diagrams: list[Diagram] = []
        for r in results:
            diagrams.extend(r)

        report.diagrams_generated = len(diagrams)
        report.elapsed_seconds = time.monotonic() - start
        logger.info(report.summary())
        return diagrams, report

    async def _generate_for_one(
        self,
        topic: Topic,
        existing: set[str],
        semaphore: asyncio.Semaphore,
        report: DiagramGenerationReport,
    ) -> list[Diagram]:
        async with semaphore:
            try:
                user_prompt = self._build_user_prompt(topic)
                response = await asyncio.to_thread(
                    self.llm.generate_json, DIAGRAM_SYSTEM_PROMPT, user_prompt,
                )
                data = self._parse_response(response.content)
                diagrams = []
                for d in data.get("diagrams", []):
                    name = (d.get("name") or "").strip()
                    spec = d.get("spec") or {}
                    description = (d.get("description") or "").strip()
                    if not name or not spec:
                        continue
                    diagram_id = generate_diagram_uid(topic.topic_id, name)
                    if diagram_id in existing:
                        report.topics_skipped_existing += 1
                        continue
                    diagrams.append(Diagram(
                        diagram_id=diagram_id,
                        renderer=DiagramRenderer.SVG,
                        render_data=spec,
                        description=description or name,
                        linked_topic_ids=[topic.topic_id],
                    ))
                logger.debug("Topic %s: %d diagrams generated", topic.topic_id, len(diagrams))
                return diagrams
            except Exception as e:
                logger.warning("Diagram generation failed for %s: %s", topic.topic_id, e)
                report.failures.append(f"{topic.topic_id}: {e}")
                return []

    def _build_user_prompt(self, topic: Topic) -> str:
        return (
            f"## Topic: {topic.topic_name}\n\n"
            f"## Explanation\n{topic.our_understanding}\n\n"
            f"## Examples\n{chr(10).join('- ' + ex for ex in topic.examples)}\n\n"
            f"Generate 1-3 teaching diagrams for this topic. Return JSON with 'diagrams' array."
        )

    @staticmethod
    def _parse_response(raw: str) -> dict:
        stripped = raw.strip()
        if stripped.startswith("```"):
            first_nl = stripped.index("\n") if "\n" in stripped else 3
            stripped = stripped[first_nl + 1:]
            if stripped.endswith("```"):
                stripped = stripped[:-3].strip()
        return json.loads(stripped)
