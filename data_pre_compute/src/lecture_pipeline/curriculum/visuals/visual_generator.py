"""Visual pre-generation: generate DiagramSpec for every concept with a visual_hint.

For each concept node whose ``visual_hint`` is not None, calls the LLM with the
design-agent system prompt to produce a DiagramSpec JSON. Validates the output
via Pydantic + semantic checks, returning a list of (concept_uid, DiagramSpec)
pairs ready for Neo4j storage.

Concurrency is handled via ``asyncio.to_thread`` (the LLM provider is sync) with
a semaphore to cap parallel calls.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field

from lecture_pipeline.curriculum.models import CurriculumExtractionResult, ExtractionNode
from lecture_pipeline.llm.base import LLMProvider

from .models import DiagramSpec
from .spec_validator import VisualSpecValidator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System prompt — identical to design_agent/backend/prompts.py
# Embedded here to keep the pipeline self-contained.
# ---------------------------------------------------------------------------

DIAGRAM_SYSTEM_PROMPT = r"""You are an expert teacher who draws clear, beautiful diagrams for students. Your goal is to make complex concepts visually intuitive — every diagram should be something you'd proudly put on a whiteboard or in a textbook. Prioritize clarity over complexity: use clean lines, generous spacing, readable labels, and logical visual flow. A student seeing your diagram for the first time should immediately understand what's happening.

You output structured JSON diagram specifications. The frontend renders using pure SVG with visx (React). All coordinates are pixel-based (origin top-left, y goes down).

## Output format

Return **only** a single JSON object. No markdown fences, no commentary, no explanation.

## Top-level schema

```
{
  "title": "string",
  "description": "string",
  "width": 900,
  "height": 650,
  "backgroundColor": "#ffffff",
  "elements": [ ... ],
  "parameters": [ ... ],
  "animations": [ ... ]
}
```

## Element types

Every element must have a `"type"` field and a unique `"id"`. All coordinate fields accept numbers or expression strings referencing parameter names.

### svg_line
`{"type": "svg_line", "id": "...", "x1": 0, "y1": 0, "x2": 100, "y2": 100, "stroke": "#000", "strokeWidth": 2, "strokeDasharray": ""}`

### svg_rect
`{"type": "svg_rect", "id": "...", "x": 0, "y": 0, "width": 100, "height": 50, "fill": "none", "stroke": "#000", "strokeWidth": 2, "rx": 0}`

### svg_circle
`{"type": "svg_circle", "id": "...", "cx": 100, "cy": 100, "r": 50, "stroke": "#000", "fill": "none", "strokeWidth": 2, "strokeDasharray": ""}`

### svg_ellipse
`{"type": "svg_ellipse", "id": "...", "cx": 100, "cy": 100, "rx": 50, "ry": 30, "stroke": "#000", "fill": "none", "strokeWidth": 2}`

### svg_path
Arbitrary SVG path data.
`{"type": "svg_path", "id": "...", "d": "M 0 0 L 100 100", "stroke": "#000", "strokeWidth": 2, "fill": "none", "strokeDasharray": ""}`

### svg_text
Plain-text label at a pixel position.
`{"type": "svg_text", "id": "...", "x": 100, "y": 50, "text": "Label", "fontSize": 14, "fill": "#000", "textAnchor": "middle", "fontWeight": "normal"}`

### svg_arc
Circular arc. Angles in degrees, 0 = right (3 o'clock), positive = clockwise in screen space.
`{"type": "svg_arc", "id": "...", "cx": 100, "cy": 100, "r": 50, "startAngle": 0, "endAngle": 90, "stroke": "#000", "strokeWidth": 2, "fill": "none", "strokeDasharray": ""}`

### svg_group
Groups child elements with an SVG transform.
`{"type": "svg_group", "id": "...", "transform": "translate(100, 50)", "elements": [...]}`

### svg_latex
KaTeX math expression at a pixel position.
`{"type": "svg_latex", "id": "...", "expression": "E = mc^{2}", "x": 100, "y": 50, "fontSize": 16, "color": "#000"}`

### svg_arrow
Line with arrowhead. Use for force vectors, ray directions, flow annotations.
`{"type": "svg_arrow", "id": "...", "x1": 0, "y1": 0, "x2": 100, "y2": 100, "stroke": "#000", "strokeWidth": 2, "strokeDasharray": ""}`

### graph
Inset plot with axes, grid, and curves at a given pixel position. Rendered as a complete visx chart.
```
{
  "type": "graph", "id": "...",
  "x": 50, "y": 50, "width": 300, "height": 200,
  "xDomain": [-10, 10], "yDomain": [-10, 10],
  "xLabel": "x", "yLabel": "y",
  "backgroundColor": "#f9f9f9", "borderColor": "#ccc",
  "curves": [{"expression": "sin(x)", "color": "steelblue", "strokeWidth": 2}],
  "showGrid": true
}
```
The `curves[].expression` is a math expression with `x` as the independent variable. Parameter names are also available as variables.

## Parameters (interactive sliders)

```
{"name": "param_name", "min": 0, "max": 10, "default": 5, "step": 0.1, "label": "Display label"}
```
Reference parameter names in any coordinate field as expression strings.

## Expression strings

Any coordinate field can be a number or an expression string.
Available math: `sin, cos, tan, sqrt, abs, PI, E, log, exp, pow, floor, ceil, min, max, atan2, asin, acos, sinh, cosh, tanh`
Use plain names — `sin(x)` not `Math.sin(x)`.

## Rules

1. **Pixel coordinates**: origin top-left, x right, y DOWN. Canvas default 900x650. Center ≈ (450, 325).
2. **svg_text** ONLY for plain-language labels. **svg_latex** for ANYTHING with math, symbols, or formulas.
   - **svg_text examples** (plain labels): "Object", "Screen", "Barrier", "Reactants", "Step 1", "5 kg block"
   - **svg_latex examples** (must use latex): "f = 10\\text{cm}", "\\theta = 30°", "F = mg", "v^2", "\\Delta x", "R_1 = 100\\,\\Omega"
   - **Rule of thumb**: if it has subscripts, superscripts, Greek letters, equals signs with variables, fractions, or any math notation → svg_latex. When in doubt, use svg_latex.
   - Write PROPER KaTeX LaTeX — not ascii approximations:
     - Fractions: `\\frac{x^2}{2}` NOT `x^2/2` or `2x2`
     - Integrals: `\\int_0^a x\\,dx` NOT `∫0a x dx`
     - Evaluated: `\\left.\\frac{x^2}{2}\\right|_0^a` NOT `x2/2|0a`
     - Superscripts: `a^{2}` NOT `a2`
   - Always double-escape backslashes in JSON: `\\frac`, `\\theta`, `\\int`
   - For step-by-step derivations, show each step as a separate svg_latex element with proper vertical spacing (increment y by ~40px per step).
3. **Clean layouts**: use the full canvas. Spread elements out. Keep labels offset from elements they describe. Place equations in a separate area (bottom or corner).
4. **Apparatus diagrams** (optics, waves, circuits): use svg_rect for barriers, svg_line/svg_arc for waves, svg_arrow for rays, graph for intensity plots.
5. **graph element** for any function plot or data chart. It renders a complete chart with axes and grid.
6. **svg_group** with `transform="translate(x,y)"` to group related elements.
7. **Color coding**: barriers #555, waves #4682b4, gravity #4CAF50, tension #FF9800, net force #D32F2F, reference lines gray dashed, labels #333.
8. **When sliders exist**, ALL dependent positions MUST be expression strings, not hardcoded numbers.
9. **Dimensionless sliders**: use normalized values (0-10 range) or dimensionless ratios instead of physical units. This ensures sliders have visible effect.
10. Every element needs a unique `id`.
11. Return pure JSON only.

Now generate the JSON for the user's request.
"""


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass
class VisualGenerationReport:
    """Tracks visual pre-generation results."""

    total_concepts: int = 0
    concepts_with_hints: int = 0
    visuals_generated: int = 0
    visuals_failed: int = 0
    errors: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    def summary(self) -> str:
        status = "OK" if not self.errors else f"ERRORS: {len(self.errors)}"
        return (
            f"Visual generation {status} — "
            f"{self.visuals_generated}/{self.concepts_with_hints} generated"
            + (f", {self.visuals_failed} failed" if self.visuals_failed else "")
            + f", {self.elapsed_seconds:.1f}s"
        )


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


def _concept_visual_uid(concept_uid: str) -> str:
    """Derive a Visual node UID from a concept UID.

    ``curriculum:physics:shm:energy`` → ``visual:physics:shm:energy``
    """
    if concept_uid.startswith("curriculum:"):
        return "visual:" + concept_uid[len("curriculum:"):]
    return "visual:" + concept_uid


def _build_user_prompt(node: ExtractionNode, subject: str) -> str:
    """Build the user prompt for DiagramSpec generation."""
    return (
        f"Generate a teaching diagram for:\n"
        f"Topic: {node.topic_name}\n"
        f"Visual: {node.visual_hint}\n"
        f"Context: {node.summary[:500]}\n"
        f"Type: {node.concept_type.value}\n"
        f"Subject: {subject}\n"
    )


def _extract_json(text: str) -> str:
    """Extract JSON from LLM response, stripping markdown fences if present."""
    stripped = text.strip()
    # Strip ```json ... ``` fences
    if stripped.startswith("```"):
        first_nl = stripped.index("\n") if "\n" in stripped else 3
        stripped = stripped[first_nl + 1:]
        if stripped.endswith("```"):
            stripped = stripped[:-3].strip()
    return stripped


class VisualGenerator:
    """Generates DiagramSpec visuals for concepts with visual_hints."""

    def __init__(self, llm: LLMProvider, *, concurrency: int = 10) -> None:
        self.llm = llm
        self.concurrency = concurrency
        self.validator = VisualSpecValidator()

    async def generate_visuals(
        self,
        extraction: CurriculumExtractionResult,
    ) -> tuple[list[tuple[str, DiagramSpec]], VisualGenerationReport]:
        """Generate DiagramSpecs for all concepts with visual_hints.

        Returns:
            Tuple of (list of (concept_uid, DiagramSpec) pairs, report).
        """
        start = time.monotonic()
        report = VisualGenerationReport(total_concepts=len(extraction.nodes))

        # Filter to concepts with visual hints
        hinted = [n for n in extraction.nodes if n.visual_hint]
        report.concepts_with_hints = len(hinted)

        if not hinted:
            logger.info("No concepts with visual_hints — skipping visual generation.")
            report.elapsed_seconds = time.monotonic() - start
            return [], report

        logger.info(
            "Generating visuals for %d/%d concepts...",
            len(hinted),
            len(extraction.nodes),
        )

        # Generate concurrently
        semaphore = asyncio.Semaphore(self.concurrency)
        tasks = [
            self._generate_one(node, extraction.subject, semaphore, report)
            for node in hinted
        ]
        results = await asyncio.gather(*tasks)

        # Collect successful results
        visuals: list[tuple[str, DiagramSpec]] = [r for r in results if r is not None]

        report.elapsed_seconds = time.monotonic() - start
        logger.info(report.summary())
        return visuals, report

    async def _generate_one(
        self,
        node: ExtractionNode,
        subject: str,
        semaphore: asyncio.Semaphore,
        report: VisualGenerationReport,
    ) -> tuple[str, DiagramSpec] | None:
        """Generate a single DiagramSpec. Returns None on failure."""
        async with semaphore:
            try:
                user_prompt = _build_user_prompt(node, subject)
                response = await asyncio.to_thread(
                    self.llm.generate_json,
                    DIAGRAM_SYSTEM_PROMPT,
                    user_prompt,
                )

                # Parse JSON
                raw_json = _extract_json(response.content)
                spec = DiagramSpec.model_validate_json(raw_json)

                # Semantic validation
                warnings = self.validator.validate(spec)
                for w in warnings:
                    logger.warning(
                        "Visual for %r: %s", node.topic_name, w
                    )

                visual_uid = _concept_visual_uid(node.uid)
                report.visuals_generated += 1
                logger.debug(
                    "Generated visual for %r: %d elements",
                    node.topic_name,
                    len(spec.elements),
                )
                return (visual_uid, spec)

            except Exception as e:
                report.visuals_failed += 1
                error_msg = f"Visual generation failed for {node.uid!r} ({node.topic_name!r}): {e}"
                report.errors.append(error_msg)
                logger.warning(error_msg)
                return None
