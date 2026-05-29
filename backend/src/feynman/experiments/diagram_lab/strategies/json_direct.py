# TODO(DEADCODE): file unused in active pipelines (precompute-gen / lecture-playback / ask-feynman). See docs/engineering/13-redundant-code-audit.md Group 1. Safe to delete.
# """JSON-direct strategy — Claude writes a full DiagramSpec as JSON.

# Wraps the existing `design_agent/backend/prompts.py:SYSTEM_PROMPT` path,
# but bypasses the cache in `design_bridge` so the testbed measures true
# latency on every run.
# """

# from __future__ import annotations

# import time
# from typing import ClassVar

# from pydantic import Field

# from feynman.agent.design_bridge import (
#     _MODELS,
#     _ensure_dictionary_completeness,
#     _get_client,
#     _load_system_prompt,
#     _parse_response,
# )
# from feynman.experiments.diagram_lab.strategies.base import (
#     GenerationStrategy,
#     StrategyOptions,
#     StrategyResult,
#     TimingBreakdown,
# )


# class JsonDirectOptions(StrategyOptions):
#     max_tokens: int = Field(default=16000, ge=1000, le=64000)
#     temperature: float = Field(default=1.0, ge=0.0, le=1.0)


# class JsonDirectStrategy(GenerationStrategy):
#     id = "json_direct"
#     display_name = "JSON direct"
#     description = (
#         "Claude writes the full DiagramSpec as JSON (existing prompts.py). "
#         "Fast on stock diagrams; geometry is whatever the LLM eyeballs."
#     )
#     category = "json"
#     supports_models: ClassVar[list[str]] = ["opus", "sonnet", "haiku"]
#     default_model = "sonnet"
#     options_model = JsonDirectOptions

#     async def generate(
#         self,
#         prompt: str,
#         model: str,
#         options: StrategyOptions,
#     ) -> StrategyResult:
#         assert isinstance(options, JsonDirectOptions)
#         system_prompt = _load_system_prompt()
#         model_id = _MODELS.get(model, model)
#         client = _get_client()

#         t_start = time.perf_counter()
#         first_token_at: float | None = None
#         accumulated = ""

#         async with client.messages.stream(
#             model=model_id,
#             max_tokens=options.max_tokens,
#             temperature=options.temperature,
#             system=system_prompt,
#             messages=[{"role": "user", "content": prompt}],
#         ) as stream:
#             async for text in stream.text_stream:
#                 if first_token_at is None:
#                     first_token_at = time.perf_counter()
#                 accumulated += text
#             final = await stream.get_final_message()

#         t_llm_done = time.perf_counter()
#         spec = _parse_response(accumulated)
#         spec = _ensure_dictionary_completeness(spec)
#         t_done = time.perf_counter()

#         warnings: list[str] = []
#         if final.stop_reason == "max_tokens":
#             warnings.append(
#                 f"Response truncated at max_tokens={options.max_tokens}; spec may be incomplete."
#             )

#         usage = final.usage
#         metadata = {
#             "input_tokens": usage.input_tokens,
#             "output_tokens": usage.output_tokens,
#             "stop_reason": final.stop_reason,
#             "element_count": len(spec.get("elements", [])),
#             "dictionary_count": len(spec.get("dictionary", {})),
#             "raw_output_chars": len(accumulated),
#         }

#         return StrategyResult(
#             spec=spec,
#             raw_output=accumulated,
#             prompt_used=system_prompt,
#             model_used=model_id,
#             timing=TimingBreakdown(
#                 total_ms=(t_done - t_start) * 1000,
#                 first_token_ms=((first_token_at - t_start) * 1000) if first_token_at else None,
#                 llm_ms=(t_llm_done - t_start) * 1000,
#                 parse_ms=(t_done - t_llm_done) * 1000,
#             ),
#             metadata=metadata,
#             warnings=warnings,
#         )


# __all__ = ["JsonDirectStrategy"]
