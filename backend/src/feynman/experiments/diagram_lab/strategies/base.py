# TODO(DEADCODE): file unused in active pipelines (precompute-gen / lecture-playback / ask-feynman). See docs/engineering/13-redundant-code-audit.md Group 1. Safe to delete.
# """Strategy plugin contract for the diagram-generation testbed.

# Each generation strategy (JSON-direct, Python-DSL, two-shot, TikZ, ...) is a
# subclass of `GenerationStrategy`. The registry auto-discovers them; the
# frontend renders the right options form by reading `options_schema`.

# Add a new strategy by dropping a single file into `strategies/` and
# subclassing `GenerationStrategy`. No router edits, no UI edits.
# """

# from __future__ import annotations

# from abc import ABC, abstractmethod
# from typing import Any, ClassVar

# from pydantic import BaseModel, Field


# class StrategyOptions(BaseModel):
#     """Base for strategy-specific knobs. Subclass per strategy."""

#     model_config = {"extra": "forbid"}


# class TimingBreakdown(BaseModel):
#     """Per-phase timings in milliseconds. Strategies fill what they have."""

#     total_ms: float
#     first_token_ms: float | None = None
#     first_element_ms: float | None = None
#     llm_ms: float | None = None
#     parse_ms: float | None = None
#     sandbox_ms: float | None = None
#     render_ms: float | None = None
#     extra: dict[str, float] = Field(default_factory=dict)


# class StrategyResult(BaseModel):
#     """Uniform output every strategy returns to the router."""

#     spec: dict[str, Any] = Field(
#         description="Validated DiagramSpec dict, ready for the frontend renderer."
#     )
#     raw_output: str = Field(
#         description=(
#             "The model's literal response (JSON text, Python source, TikZ source) — "
#             "shown verbatim in the inspect panel for debugging prompt behavior."
#         )
#     )
#     prompt_used: str = Field(
#         description=(
#             "The exact system prompt sent to the model. Snapshot at run-time so "
#             "you can correlate output quality with prompt version."
#         )
#     )
#     model_used: str = Field(description="Resolved model id (e.g. 'claude-sonnet-4...').")
#     timing: TimingBreakdown
#     metadata: dict[str, Any] = Field(
#         default_factory=dict,
#         description=(
#             "Per-strategy diagnostics — element counts, token usage, intermediate "
#             "plan, sandbox warnings, etc. Surfaced in the metadata inspect tab."
#         ),
#     )
#     warnings: list[str] = Field(default_factory=list)


# class StrategyAvailability(BaseModel):
#     """Why a strategy is or isn't ready to run."""

#     available: bool
#     reason: str | None = None


# class StrategyDescriptor(BaseModel):
#     """Plugin-discovery surface returned by `GET /api/diagtest/strategies`."""

#     id: str
#     display_name: str
#     description: str
#     category: str = Field(description="Grouping for the UI: 'json' | 'python' | 'latex' | 'other'.")
#     supports_models: list[str]
#     default_model: str
#     options_schema: dict[str, Any] = Field(description="JSON Schema for the options form.")
#     options_defaults: dict[str, Any] = Field(default_factory=dict)
#     availability: StrategyAvailability


# class GenerationStrategy(ABC):
#     """Implement one of these per generation approach."""

#     id: ClassVar[str]
#     display_name: ClassVar[str]
#     description: ClassVar[str]
#     category: ClassVar[str] = "other"
#     supports_models: ClassVar[list[str]]
#     default_model: ClassVar[str]
#     options_model: ClassVar[type[StrategyOptions]] = StrategyOptions

#     def availability(self) -> StrategyAvailability:
#         """Override when a strategy needs runtime deps (e.g. pdflatex)."""
#         return StrategyAvailability(available=True)

#     def descriptor(self) -> StrategyDescriptor:
#         schema = self.options_model.model_json_schema()
#         defaults = self.options_model().model_dump()
#         return StrategyDescriptor(
#             id=self.id,
#             display_name=self.display_name,
#             description=self.description,
#             category=self.category,
#             supports_models=list(self.supports_models),
#             default_model=self.default_model,
#             options_schema=schema,
#             options_defaults=defaults,
#             availability=self.availability(),
#         )

#     def parse_options(self, raw: dict[str, Any] | None) -> StrategyOptions:
#         return self.options_model.model_validate(raw or {})

#     @abstractmethod
#     async def generate(
#         self,
#         prompt: str,
#         model: str,
#         options: StrategyOptions,
#     ) -> StrategyResult:
#         """Run the strategy. Must return a validated StrategyResult."""
#         raise NotImplementedError
