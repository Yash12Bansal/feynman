"""System prompt for the LessonDiagramGenerator (doc 19 Phase D).

Wraps the base DIAGRAM_SYSTEM_PROMPT (palette, layout, dictionary mandate)
with the Phase D coupling contract: the lesson plan has ALREADY declared the
element_ids the choreography commits to referring to. The generated spec
MUST contain every declared id in BOTH `elements[]` (so the SVG node exists
with `data-design-element="<id>"` for DOM-based annotations) AND
`dictionary{}` (so the fallback-bounds path has metadata to work with).

If either axis is missing for any required id, the planner reports the gap
and asks for a self-correcting retry. The base prompt does not enforce this
on its own — it tells the LLM that a dictionary is "required", but does not
constrain WHICH keys must appear. Phase D closes that gap.
"""

from __future__ import annotations

from lecture_pipeline_v2.curriculum.enrichment.diagrams import DIAGRAM_SYSTEM_PROMPT


_PHASE_D_PREAMBLE = """\
# Phase D — Diagram coupling contract

You are generating a DiagramSpec for a lesson that has ALREADY been planned. \
The choreography (the lesson's "stage directions") was written BEFORE you \
got this task, and it commits to referring to specific elements by stable \
`element_id` strings. The user message lists those `element_id`s under \
`required_elements`.

## The hard contract

For EVERY `element_id` listed in `required_elements`, your output spec MUST \
satisfy BOTH of the following:

1. **There exists an entry in `elements[]` with `id: "<element_id>"`.** \
This is the load-bearing link — the frontend tags this SVG node with \
`data-design-element="<element_id>"` and annotation primitives (focus, \
trace, mark_point, point_at, write_margin) target it via DOM query. If the \
node does not exist, the annotation silently no-ops at playback time.

2. **There exists an entry in `dictionary{}` with key `"<element_id>"`.** \
This carries the role / semantic / position / spatial_relations / bounds \
metadata. It is the runtime's fallback when DOM lookup fails (e.g., during \
mount transitions). The `bounds` field is REQUIRED for required elements — \
[x, y, width, height] in SVG coords. Without bounds, primitives like \
TraceOverlay silently fail.

## What you may add freely

You may add additional elements beyond the required list — axes, labels, \
arrows, ground lines, framing. The required list is a FLOOR, not a ceiling. \
Adding helpful context is encouraged; omitting a required id is rejected.

## What you must NOT do

- Rename required `element_id`s. Use the exact strings from \
  `required_elements`. The choreography refers to them verbatim.
- Use generic ids (`shape-1`, `arrow`, `path`) — the required ids are \
  kebab-case and semantic; your additional elements should follow the same \
  convention but the required ones MUST match verbatim.
- Skip the `dictionary` for required elements. Even if the element itself \
  is "obvious" (a line, a circle), the dictionary entry is what the runtime \
  inspects when the DOM lookup misses.
- Omit `bounds` from any required-element dictionary entry. If the shape is \
  truly irregular, compute a tight axis-aligned bounding box and use that — \
  do NOT emit `null`.

## Failure mode

If you omit a required element from either `elements[]` or `dictionary{}`, \
your spec will be rejected and you will be asked to retry with the missing \
ids called out. The retry budget is small (one extra attempt). Plan for a \
first-try pass.

Read the base design rules below and then produce the spec.

---

"""


LESSON_DIAGRAM_SYSTEM_PROMPT = _PHASE_D_PREAMBLE + DIAGRAM_SYSTEM_PROMPT
