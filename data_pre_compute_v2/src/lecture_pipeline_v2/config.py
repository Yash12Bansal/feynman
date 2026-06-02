"""Configuration models for the v2 pipeline.

Loaded from config.yaml; API keys filled from env on demand.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

# Providers that need an API key, and the env var(s) each reads. `ollama` is
# local and keyless. This is the SINGLE place provider→env-var mapping lives;
# both `PipelineConfig.load()` and `LLMConfig.for_override()` go through it.
_PROVIDER_ENV_KEYS: dict[str, tuple[str, ...]] = {
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
}


def api_key_for_provider(provider: str) -> str | None:
    """Resolve the API key for a provider from the environment.

    Returns the first non-empty matching env var, or None (ollama / unknown
    providers are keyless). Gemini accepts either GEMINI_API_KEY or the
    Google-standard GOOGLE_API_KEY.
    """
    for env_var in _PROVIDER_ENV_KEYS.get(provider, ()):
        value = os.environ.get(env_var)
        if value:
            return value
    return None


class LLMConfig(BaseModel):
    provider: Literal["openai", "anthropic", "ollama", "gemini"] = "anthropic"
    model: str = "claude-sonnet-4-6"
    base_url: str | None = None
    temperature: float = 0.3
    max_tokens: int = 16384
    api_key: str | None = None

    def for_override(
        self, provider: str | None = None, model: str | None = None
    ) -> LLMConfig:
        """Return a copy with provider/model overridden for a single role.

        Used by per-role overrides (judge, vision-QA) so they can pin a
        different model than the main authoring path. When the provider
        changes, the API key is re-resolved from the environment so the right
        SDK gets the right key. Returns ``self`` UNCHANGED when no effective
        override is requested — callers identity-check this to reuse the main
        provider instance instead of building a second client.
        """
        new_provider = provider or self.provider
        new_model = model or self.model
        if new_provider == self.provider and new_model == self.model:
            return self
        api_key = (
            self.api_key
            if new_provider == self.provider
            else api_key_for_provider(new_provider)
        )
        return self.model_copy(
            update={
                "provider": new_provider,
                "model": new_model,
                "api_key": api_key,
            }
        )


class PDFConfig(BaseModel):
    ocr_threshold: int = 50
    image_dpi: int = 200
    ocr_language: str = "eng"


class TTSConfig(BaseModel):
    provider: Literal["kokoro"] = "kokoro"
    model: str = "kokoro-v1.0"
    voice: str = "af_heart"
    sample_rate: int = 24000
    output_format: Literal["mp3", "ogg", "wav"] = "mp3"
    pause_short_ms: int = 250
    pause_long_ms: int = 750


class JudgeModelConfig(BaseModel):
    provider: Literal["openai", "anthropic", "ollama", "gemini"]
    model: str


class ValidationConfig(BaseModel):
    judge_models: list[JudgeModelConfig] = Field(default_factory=list)
    judge_agreement_threshold: float = 0.66
    tts_qa_drift_threshold: float = 0.05
    gap_fill_max_retries: int = 2


class Neo4jConfig(BaseModel):
    uri: str = "bolt://localhost:7687"
    username: str = "neo4j"
    password: str = "password"
    database: str = "neo4j"


class EmbeddingConfig(BaseModel):
    provider: Literal["sentence_transformers", "openai"] = "sentence_transformers"
    model: str = "sentence-transformers/all-MiniLM-L6-v2"
    dimensions: int = 384
    batch_size: int = 64
    device: str = "auto"


class ArtifactsConfig(BaseModel):
    base_dir: str = "./artifacts"
    audio_dir: str = "audio"
    diagram_dir: str = "diagrams"
    animation_dir: str = "animations"
    runs_dir: str = "runs"
    url_prefix: str = "file://./artifacts"


class ViewportConfig(BaseModel):
    width: int = 1600
    height: int = 900


class SlideRegionConfig(BaseModel):
    x: int = 30
    y: int = 50
    width: int = 900
    height: int = 800
    padding: int = 20


class NotebookRegionConfig(BaseModel):
    x: int = 970
    y: int = 50
    width: int = 600
    height: int = 800
    padding: int = 30


class DiagramFitConfig(BaseModel):
    max_scale: float = 1.0
    fit: Literal["contain"] = "contain"


class MeasurementConfig(BaseModel):
    mode: Literal["headless_browser"] = "headless_browser"
    cache_dir: str = "./artifacts/measurement_cache"
    page_path: str = "./tools/measurement_page.html"
    # Path to the frontend CSS file, hashed into the cache key so CSS edits
    # auto-invalidate measurements. Resolved relative to the pipeline's CWD.
    css_hash_path: str = "../frontend/src/engine/whiteboard/split/SplitBoard.css"


class PaginationConfig(BaseModel):
    lookahead_seconds: float = 20.0
    overflow_safety_margin_px: float = 8.0


class LayoutConfig(BaseModel):
    """Phase 3 layout + pagination config.

    Geometry mirrors design doc §7.3. The preview screen pins SplitBoard
    to these exact pixel dimensions via `.sb-root--preview`; the live
    agent path stays responsive and ignores this config.
    """

    viewport: ViewportConfig = Field(default_factory=ViewportConfig)
    slide: SlideRegionConfig = Field(default_factory=SlideRegionConfig)
    notebook: NotebookRegionConfig = Field(default_factory=NotebookRegionConfig)
    block_spacing_px: int = 12
    block_default_widths: dict[str, int] = Field(
        default_factory=lambda: {
            "SECTION": 540,
            "EQUATION": 540,
            "STEP": 520,
            "KEY": 540,
            "TEXT": 540,
            "ANSWER": 540,
        }
    )
    diagram: DiagramFitConfig = Field(default_factory=DiagramFitConfig)
    measurement: MeasurementConfig = Field(default_factory=MeasurementConfig)
    pagination: PaginationConfig = Field(default_factory=PaginationConfig)


class DiagramQAConfig(BaseModel):
    """Phase 4c — DiagramQA vision-loop config.

    `provider`/`model` are OPTIONAL overrides. Left unset (the default),
    DiagramQA follows the main `llm` switch — so a single model change covers
    vision QA too. Set them to pin a specific vision-capable model (e.g. keep
    QA on a strong vision model while authoring on a cheaper one). Note: the
    chosen model MUST support image input; DiagramQA degrades gracefully
    (skips, never blocks) if it doesn't.
    """

    enabled: bool = True
    provider: str | None = None
    model: str | None = None
    max_retries: int = 2
    min_score: int = 3


class LessonPipelineConfig(BaseModel):
    """Phase H (doc 19) — doc-19 stack runtime config.

    When `use_lesson_pipeline` is True at the enrichment level, the pipeline
    replaces phases 7b–7g (ConceptPlanner → DiagramSpecGenerator → DiagramQA →
    BeatNarrationWriter → LengthEnforcer → ScriptAssembler) with the doc-19
    stack: LessonPlanner → LessonDiagramGenerator → DiagramQA → LessonNarrator
    → LessonProsody, orchestrated by LessonQualityGate.

    `max_quality_retries` is the per-stage budget for quality regen (PlanJudge
    or DiagramQA flagged the artifact below threshold). Pydantic retries are
    INDEPENDENT (the planner/generator each have their own internal 2-attempt
    loop) — this knob layers on top.
    """

    max_quality_retries: int = 1
    plan_min_score: int = 3
    diagram_min_score: int = 3
    # Optional override for the LLM-as-judge (PlanJudge). Unset → follows the
    # main `llm` switch. Pinning a DIFFERENT model/provider than the author is
    # good practice: it reduces correlated errors (a model is a poor judge of
    # its own blind spots).
    judge_provider: str | None = None
    judge_model: str | None = None


class EnrichmentConfig(BaseModel):
    """Phase 4c+4d — enrichment-stage knobs.

    Phase 4c: per-beat DiagramSpecGenerator + DiagramQA (vision loop).
    Phase 4d: BeatNarrationWriter + LengthEnforcer + ScriptAssembler.
    Phase H (doc 19): when `use_lesson_pipeline` is True, the doc-19 stack
    replaces the 4c-4d chain. Defaults to True — the legacy path is kept
    behind the flag for A/B comparison until the doc-19 path is validated
    end-to-end.
    """

    diagram_qa: DiagramQAConfig = Field(default_factory=DiagramQAConfig)
    # Phase H — doc-19 path toggle. Default ON.
    use_lesson_pipeline: bool = True
    lesson_pipeline: LessonPipelineConfig = Field(default_factory=LessonPipelineConfig)


class PipelineConfig(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    pdf: PDFConfig = Field(default_factory=PDFConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    layout: LayoutConfig = Field(default_factory=LayoutConfig)
    enrichment: EnrichmentConfig = Field(default_factory=EnrichmentConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    neo4j: Neo4jConfig = Field(default_factory=Neo4jConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    artifacts: ArtifactsConfig = Field(default_factory=ArtifactsConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> PipelineConfig:
        path = Path(path)
        if not path.exists():
            return cls()
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return cls(**data)

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> PipelineConfig:
        if config_path:
            cfg = cls.from_yaml(config_path)
        elif Path("config.yaml").exists():
            cfg = cls.from_yaml("config.yaml")
        else:
            cfg = cls()

        if cfg.llm.api_key is None:
            cfg.llm.api_key = api_key_for_provider(cfg.llm.provider)

        return cfg
