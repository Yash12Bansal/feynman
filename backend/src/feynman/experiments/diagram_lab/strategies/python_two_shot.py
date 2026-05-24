# ruff: noqa: RUF001
"""Python two-shot strategy — plan first, then write canvas_dsl code.

Hypothesis: a cheap planning pass produces a tighter, more accurate
script than a single end-to-end call. Each phase uses an independent
model so we can mix-and-match (e.g. haiku-plans → opus-codes).

Inspect tab surfaces the intermediate plan so you can iterate on the
planning prompt without touching the codegen prompt.
"""

from __future__ import annotations

import time
from typing import ClassVar, Literal

from pydantic import Field

from feynman.agent.design_bridge import (
    _MODELS,
    _ensure_dictionary_completeness,
    _extract_python,
    _get_client,
    _load_python_system_prompt,
)
from feynman.experiments.diagram_lab.strategies.base import (
    GenerationStrategy,
    StrategyOptions,
    StrategyResult,
    TimingBreakdown,
)
from feynman.visuals.sandbox import EXEC_TIMEOUT_SECONDS, SandboxError, execute_python_diagram

_PLAN_SYSTEM_PROMPT = """You are a teaching designer planning a math diagram. \
Given a prompt, return a tight structured plan that another model will turn into \
a Python diagram script. Be concise — every word matters.

Output exactly these sections in this order, no markdown headers, no prose intro:

INTENT: one sentence — what concept this diagram makes visible.

ELEMENTS: bullet list. Each line is `<role>: <short geometric description>`. \
Example: `hypotenuse: line from B(150,400) to A(150,150) length 250`. \
Use rough integer coords on a 900×650 canvas, origin top-left, +y down. \
Anchor the diagram around center (450, 325).

KEY GEOMETRY: one or two lines naming the trig/algebraic identities that \
constrain the layout. Example: `Right angle at B → tan(A) = opposite/adjacent`. \
Skip if not applicable.

LABELS: bullet list of textual labels to render (variable letters, lengths, \
angle values). Each line: `<position>: <label text>`. Example: `midpoint of AB: \
"5 cm"`.

COLOR HINTS: 1–3 lines pairing roles to the standard palette \
(cyan #7fd4ff = forces/highlights, green #7fff9f = correct values, \
pink #ff7fc6 = callouts, amber #ffe27f = angles/measurements).

Stop. No closing remarks."""


PlannerStyle = Literal["structured", "freeform"]


class PythonTwoShotOptions(StrategyOptions):
    planner_model: str = Field(
        default="haiku",
        description="Model id for the planning pass — cheap is fine.",
    )
    planner_max_tokens: int = Field(default=1200, ge=200, le=8000)
    coder_max_tokens: int = Field(default=8000, ge=1000, le=32000)
    coder_temperature: float = Field(default=1.0, ge=0.0, le=1.0)
    sandbox_timeout_s: float = Field(default=EXEC_TIMEOUT_SECONDS, ge=0.5, le=10.0)
    planner_style: PlannerStyle = Field(
        default="structured",
        description=(
            "'structured' uses the INTENT/ELEMENTS/... template above. "
            "'freeform' just asks for a 5-line natural-language sketch."
        ),
    )


_FREEFORM_PLANNER_PROMPT = """You are a teaching designer. In 4–6 lines, sketch \
the key visual elements for a math diagram described below. Name the geometric \
shapes, rough coordinates on a 900×650 canvas, and any labels. No code yet."""


class PythonTwoShotStrategy(GenerationStrategy):
    id = "python_two_shot"
    display_name = "Python two-shot (plan → code)"
    description = (
        "First call (cheap model) produces a structured plan; second call writes "
        "the canvas_dsl Python given the plan. Often more accurate on complex "
        "diagrams at the cost of one extra LLM round-trip."
    )
    category = "python"
    supports_models: ClassVar[list[str]] = ["opus", "sonnet", "haiku"]
    default_model = "sonnet"
    options_model = PythonTwoShotOptions

    async def generate(
        self,
        prompt: str,
        model: str,
        options: StrategyOptions,
    ) -> StrategyResult:
        assert isinstance(options, PythonTwoShotOptions)
        coder_prompt = _load_python_system_prompt()
        client = _get_client()

        t_start = time.perf_counter()

        # ── Phase 1: plan ─────────────────────────────────────
        planner_system = (
            _PLAN_SYSTEM_PROMPT
            if options.planner_style == "structured"
            else _FREEFORM_PLANNER_PROMPT
        )
        planner_model_id = _MODELS.get(options.planner_model, options.planner_model)

        plan_accum = ""
        async with client.messages.stream(
            model=planner_model_id,
            max_tokens=options.planner_max_tokens,
            system=planner_system,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            async for text in stream.text_stream:
                plan_accum += text
            planner_final = await stream.get_final_message()

        t_plan_done = time.perf_counter()
        plan_text = plan_accum.strip()

        # ── Phase 2: write code given plan ───────────────────
        coder_model_id = _MODELS.get(model, model)
        coder_user_message = (
            f"Original prompt:\n{prompt.strip()}\n\n"
            f"Design plan (use this as the spec — coordinates and roles are advisory, "
            f"refine them with the geometric helpers):\n{plan_text}"
        )

        code_accum = ""
        coder_first_token_at: float | None = None
        async with client.messages.stream(
            model=coder_model_id,
            max_tokens=options.coder_max_tokens,
            temperature=options.coder_temperature,
            system=coder_prompt,
            messages=[{"role": "user", "content": coder_user_message}],
        ) as stream:
            async for text in stream.text_stream:
                if coder_first_token_at is None:
                    coder_first_token_at = time.perf_counter()
                code_accum += text
            coder_final = await stream.get_final_message()

        t_code_done = time.perf_counter()
        code = _extract_python(code_accum)
        if not code:
            raise ValueError("python_two_shot: coder returned no Python.")

        try:
            canvas = await execute_python_diagram(code, timeout=options.sandbox_timeout_s)
        except SandboxError as exc:
            raise ValueError(f"python_two_shot sandbox failure: {exc}") from exc

        t_sandbox_done = time.perf_counter()
        spec = _ensure_dictionary_completeness(canvas.export())
        t_done = time.perf_counter()

        warnings: list[str] = []
        if planner_final.stop_reason == "max_tokens":
            warnings.append("Planner response truncated; plan may be incomplete.")
        if coder_final.stop_reason == "max_tokens":
            warnings.append("Coder response truncated; script may be cut off.")

        metadata = {
            "planner_model": planner_model_id,
            "coder_model": coder_model_id,
            "plan_text": plan_text,
            "plan_chars": len(plan_text),
            "code_chars": len(code),
            "planner_input_tokens": planner_final.usage.input_tokens,
            "planner_output_tokens": planner_final.usage.output_tokens,
            "coder_input_tokens": coder_final.usage.input_tokens,
            "coder_output_tokens": coder_final.usage.output_tokens,
            "element_count": len(spec.get("elements", [])),
            "dictionary_count": len(spec.get("dictionary", {})),
        }

        return StrategyResult(
            spec=spec,
            raw_output=f"# === PLAN ===\n{plan_text}\n\n# === CODE ===\n{code_accum}",
            prompt_used=(
                f"--- PLANNER SYSTEM ---\n{planner_system}\n\n--- CODER SYSTEM ---\n{coder_prompt}"
            ),
            model_used=f"{planner_model_id} → {coder_model_id}",
            timing=TimingBreakdown(
                total_ms=(t_done - t_start) * 1000,
                first_token_ms=((coder_first_token_at - t_start) * 1000)
                if coder_first_token_at
                else None,
                llm_ms=(t_code_done - t_start) * 1000,
                sandbox_ms=(t_sandbox_done - t_code_done) * 1000,
                parse_ms=(t_done - t_sandbox_done) * 1000,
                extra={
                    "plan_ms": (t_plan_done - t_start) * 1000,
                    "code_ms": (t_code_done - t_plan_done) * 1000,
                },
            ),
            metadata=metadata,
            warnings=warnings,
        )


__all__ = ["PythonTwoShotStrategy"]
