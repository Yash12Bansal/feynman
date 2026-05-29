# TODO(DEADCODE): file unused in active pipelines (precompute-gen / lecture-playback / ask-feynman). See docs/engineering/13-redundant-code-audit.md Group 1. Safe to delete.
# """LLM-based annotation injector for the testbed.

# Mirrors how the live teaching agent decides annotations: given the current
# diagram and a free-text intent ("circle the hypotenuse"), pick a target
# element + annotation kind. Returns the same instruction shape the frontend
# SlideAnnotationLayer already consumes.

# Uses Haiku — fast and cheap, enough for this routing task.
# """

# from __future__ import annotations

# import json
# import re
# import time
# from typing import Any, Literal

# from pydantic import BaseModel, Field

# from feynman.agent.design_bridge import _MODELS, _get_client

# AnnotationKind = Literal["pin_label", "draw_callout", "bracket", "highlight_pulse"]


# class AnnotationRequest(BaseModel):
#     spec: dict[str, Any] = Field(description="The current DiagramSpec on the board.")
#     intent: str = Field(description="Free-text user intent (e.g. 'circle the hypotenuse').")
#     model: str = Field(default="haiku")


# class AnnotationResponse(BaseModel):
#     instruction: dict[str, Any]
#     latency_ms: float
#     raw_output: str
#     chosen_target: dict[str, Any] | None = None


# _INJECTOR_SYSTEM_PROMPT = """You convert a teacher's annotation intent into a single \
# structured annotation instruction for a diagram currently on the board.

# You will receive:
# 1. The diagram's dictionary — element id → {role, semantic, position}
# 2. A list of element ids and types currently rendered
# 3. The teacher's free-text intent

# Pick the most useful annotation kind for the intent, choose a target, and return a \
# single JSON object — no prose, no fences. Use this exact shape based on kind:

# PIN LABEL (a short label tag near an element):
# {
#   "type": "pin_label",
#   "target_element_id": "<id from the list>",
#   "target": {"kind": "id", "value": "<id>"},  // or {"kind":"role","value":"<role>"}
#   "text": "<the label text, ≤20 chars>",
#   "position": "above" | "below" | "left" | "right"
# }

# DRAW CALLOUT (a longer text bubble pointing at the element):
# {
#   "type": "draw_callout",
#   "target_element_id": "<id>",
#   "target": {"kind": "id", "value": "<id>"},
#   "text": "<one-sentence explanation, ≤80 chars>",
#   "direction": "above" | "below" | "left" | "right"
# }

# BRACKET (highlights a span between two elements):
# {
#   "type": "bracket",
#   "element_a_id": "<id>",
#   "element_b_id": "<id>",
#   "label": "<short label, ≤20 chars>",
#   "side": "above" | "below" | "left" | "right"
# }

# HIGHLIGHT PULSE (flashes attention onto one element):
# {
#   "type": "highlight_pulse",
#   "target_element_id": "<id>",
#   "target": {"kind": "id", "value": "<id>"},
#   "color": "cyan" | "amber" | "green" | "magenta",
#   "duration_ms": 1200
# }

# Rules:
# - Always include the structured `target` field where the schema has it; \
#   it gives the frontend a stable lookup if ids change.
# - If the intent matches a `role` from the dictionary, prefer \
#   `{"kind":"role","value":"<role>"}` — robust across regenerations.
# - Pick `highlight_pulse` for short-lived attention; `pin_label` for a \
#   tag that should stay; `draw_callout` for explanation text; `bracket` only \
#   when the intent talks about spanning two things.
# - If the intent is ambiguous or no element fits, choose the closest match and \
#   return it anyway — never return prose, never refuse.

# Stop. Return one JSON object."""


# def _summarize_spec(spec: dict[str, Any]) -> str:
#     """Compact view of the spec for the prompt — id + type + role only."""
#     dictionary = spec.get("dictionary") or {}
#     lines = ["DICTIONARY (id → role · semantic):"]
#     if not dictionary:
#         lines.append("  (empty — match by id or position)")
#     else:
#         for el_id, meta in dictionary.items():
#             role = meta.get("role", "")
#             semantic = meta.get("semantic", "")
#             position = meta.get("position", "")
#             lines.append(f"  {el_id}: {role} · {position} · {semantic[:60]}")

#     elements = spec.get("elements") or []
#     lines.append("\nELEMENT IDS (in render order):")
#     seen_ids = set()
#     for el in elements:
#         if isinstance(el, dict):
#             el_id = el.get("id")
#             if el_id and el_id not in seen_ids:
#                 lines.append(f"  {el_id} [{el.get('type', '?')}]")
#                 seen_ids.add(el_id)
#     if not seen_ids:
#         lines.append("  (no element ids found)")

#     if spec.get("_tikz_svg"):
#         lines.append(
#             "\nNote: this diagram was rendered via TikZ — element ids are not stamped. "
#             "Use intent-derived target role rather than id, or skip the target field."
#         )

#     return "\n".join(lines)


# _JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


# def _extract_json_object(text: str) -> dict[str, Any]:
#     fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
#     if fence:
#         text = fence.group(1)
#     m = _JSON_OBJ_RE.search(text)
#     if not m:
#         raise ValueError(f"injector: no JSON object in response: {text[:200]}")
#     return json.loads(m.group(0))


# async def inject_annotation(req: AnnotationRequest) -> AnnotationResponse:
#     client = _get_client()
#     model_id = _MODELS.get(req.model, req.model)
#     summary = _summarize_spec(req.spec)
#     user_msg = f"{summary}\n\nINTENT: {req.intent.strip()}"

#     t_start = time.perf_counter()
#     accumulated = ""
#     async with client.messages.stream(
#         model=model_id,
#         max_tokens=600,
#         system=_INJECTOR_SYSTEM_PROMPT,
#         messages=[{"role": "user", "content": user_msg}],
#     ) as stream:
#         async for chunk in stream.text_stream:
#             accumulated += chunk
#         await stream.get_final_message()
#     latency_ms = (time.perf_counter() - t_start) * 1000

#     instruction = _extract_json_object(accumulated)
#     chosen_target: dict[str, Any] | None = None
#     if "target" in instruction:
#         chosen_target = instruction["target"]
#     elif "target_element_id" in instruction:
#         chosen_target = {"kind": "id", "value": instruction["target_element_id"]}

#     return AnnotationResponse(
#         instruction=instruction,
#         latency_ms=latency_ms,
#         raw_output=accumulated,
#         chosen_target=chosen_target,
#     )
