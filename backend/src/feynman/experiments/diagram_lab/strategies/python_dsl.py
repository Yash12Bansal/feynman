"""Python DSL strategy — Claude writes Python using canvas_dsl; sandbox runs it.

Wraps the existing Phase-3 path. Geometric helpers (`polar`,
`perpendicular_to`, `intersect`) let the LLM compute exact coords instead
of guessing — usually the right baseline for math.
"""

from __future__ import annotations

import time
from typing import ClassVar

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


class PythonDslOptions(StrategyOptions):
    max_tokens: int = Field(default=8000, ge=1000, le=64000)
    temperature: float = Field(default=1.0, ge=0.0, le=1.0)
    sandbox_timeout_s: float = Field(default=EXEC_TIMEOUT_SECONDS, ge=0.5, le=10.0)


class PythonDslStrategy(GenerationStrategy):
    id = "python_dsl"
    display_name = "Python DSL (canvas_dsl)"
    description = (
        "Claude writes a Python script using the canvas_dsl library; sandbox "
        "executes it. Geometric helpers compute exact coordinates — strong "
        "for math (triangles, conics, perpendiculars, intersections)."
    )
    category = "python"
    supports_models: ClassVar[list[str]] = ["opus", "sonnet", "haiku"]
    default_model = "sonnet"
    options_model = PythonDslOptions

    async def generate(
        self,
        prompt: str,
        model: str,
        options: StrategyOptions,
    ) -> StrategyResult:
        assert isinstance(options, PythonDslOptions)
        system_prompt = _load_python_system_prompt()
        model_id = _MODELS.get(model, model)
        client = _get_client()

        t_start = time.perf_counter()
        first_token_at: float | None = None
        accumulated = ""

        async with client.messages.stream(
            model=model_id,
            max_tokens=options.max_tokens,
            temperature=options.temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            async for text in stream.text_stream:
                if first_token_at is None:
                    first_token_at = time.perf_counter()
                accumulated += text
            final = await stream.get_final_message()

        t_llm_done = time.perf_counter()
        code = _extract_python(accumulated)
        if not code:
            raise ValueError("python_dsl: model returned no Python code.")

        try:
            canvas = await execute_python_diagram(code, timeout=options.sandbox_timeout_s)
        except SandboxError as exc:
            raise ValueError(f"python_dsl sandbox failure: {exc}") from exc

        t_sandbox_done = time.perf_counter()
        spec = _ensure_dictionary_completeness(canvas.export())
        t_done = time.perf_counter()

        warnings: list[str] = []
        if final.stop_reason == "max_tokens":
            warnings.append(
                f"Response truncated at max_tokens={options.max_tokens}; the script may be cut off."
            )

        usage = final.usage
        metadata = {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "stop_reason": final.stop_reason,
            "element_count": len(spec.get("elements", [])),
            "dictionary_count": len(spec.get("dictionary", {})),
            "code_chars": len(code),
            "raw_output_chars": len(accumulated),
            "sandbox_timeout_s": options.sandbox_timeout_s,
        }

        return StrategyResult(
            spec=spec,
            raw_output=accumulated,
            prompt_used=system_prompt,
            model_used=model_id,
            timing=TimingBreakdown(
                total_ms=(t_done - t_start) * 1000,
                first_token_ms=((first_token_at - t_start) * 1000) if first_token_at else None,
                llm_ms=(t_llm_done - t_start) * 1000,
                sandbox_ms=(t_sandbox_done - t_llm_done) * 1000,
                parse_ms=(t_done - t_sandbox_done) * 1000,
            ),
            metadata=metadata,
            warnings=warnings,
        )


__all__ = ["PythonDslStrategy"]
