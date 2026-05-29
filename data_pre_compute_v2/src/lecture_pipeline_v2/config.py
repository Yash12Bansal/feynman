"""Configuration models for the v2 pipeline.

Loaded from config.yaml; API keys filled from env on demand.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    provider: Literal["openai", "anthropic", "ollama"] = "anthropic"
    model: str = "claude-sonnet-4-6"
    base_url: str | None = None
    temperature: float = 0.3
    max_tokens: int = 16384
    api_key: str | None = None


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
    provider: Literal["openai", "anthropic", "ollama"]
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


# TODO(DEADCODE): legacy 7c-7g config — values no longer read once the legacy stack is removed (kept as an EnrichmentConfig field default so not commented here). See docs/engineering/13-redundant-code-audit.md Group 3.
class PerBeatDiagramsConfig(BaseModel):
    """Phase 4c — per-beat DiagramSpecGenerator config.

    `mode="direct"` is the only wired path; `"auto"` aliases to `"direct"`;
    `"python"` raises NotImplementedError (the canvas_dsl sandbox lives in
    backend/src/feynman/agent/design_bridge.py — porting into v2 is a future
    sub-phase).
    """

    enabled: bool = True
    mode: Literal["direct", "auto", "python"] = "direct"
    concurrency: int = 5
    temperature: float = 0.1


class DiagramQAConfig(BaseModel):
    """Phase 4c — DiagramQA vision-loop config."""

    enabled: bool = True
    model: str = "claude-sonnet-4-20250514"
    max_retries: int = 2
    min_score: int = 3


# TODO(DEADCODE): legacy 7c-7g config — values no longer read once the legacy stack is removed (kept as an EnrichmentConfig field default so not commented here). See docs/engineering/13-redundant-code-audit.md Group 3.
class BeatNarrationConfig(BaseModel):
    """Phase 4d — per-beat narration writer config.

    One LLM call per beat (whose `TeachingBeat` was emitted by ConceptPlanner).
    `target_wps` (English speech rate) drives `target_words = target_seconds * target_wps`
    inside the user prompt and the seconds estimator.
    """

    enabled: bool = True
    model: str = "claude-sonnet-4-20250514"
    concurrency: int = 5
    target_wps: float = 2.5
    min_target_seconds: int = 5
    max_target_seconds: int = 90


# TODO(DEADCODE): legacy 7c-7g config — values no longer read once the legacy stack is removed (kept as an EnrichmentConfig field default so not commented here). See docs/engineering/13-redundant-code-audit.md Group 3.
class LengthEnforcerConfig(BaseModel):
    """Phase 4d — deterministic chapter-length trim algorithm config.

    `budget_tolerance` is the soft window (e.g. 1.1 = up to 110% of the chapter's
    `length_budget_seconds` accepted without trimming). `hard_ceiling` (1.3) is
    the never-block ceiling — over this, we log a warning and flag the chapter
    `needs_review=True`, but always accept.
    """

    enabled: bool = True
    budget_tolerance: float = 1.1
    hard_ceiling: float = 1.3


# TODO(DEADCODE): legacy 7c-7g config — values no longer read once the legacy stack is removed (kept as an EnrichmentConfig field default so not commented here). See docs/engineering/13-redundant-code-audit.md Group 3.
class ScriptAssemblerConfig(BaseModel):
    """Phase 4d — stitches per-beat narrations into per-topic ChapterScript shape.

    Phase 4e: flipped `use_for_playback` to `True` and removed ScriptWriter
    from the pipeline. The flag stays in config for explicitness (acts as a
    kill switch; setting `False` produces no audio since ScriptWriter is gone).
    """

    enabled: bool = True
    use_for_playback: bool = True
    pause_between_beats: Literal["short", "long"] = "short"
    pause_between_topics: Literal["short", "long"] = "long"


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


class EnrichmentConfig(BaseModel):
    """Phase 4c+4d — enrichment-stage knobs.

    Phase 4c: per-beat DiagramSpecGenerator + DiagramQA (vision loop).
    Phase 4d: BeatNarrationWriter + LengthEnforcer + ScriptAssembler.
    Phase H (doc 19): when `use_lesson_pipeline` is True, the doc-19 stack
    replaces the 4c-4d chain. Defaults to True — the legacy path is kept
    behind the flag for A/B comparison until the doc-19 path is validated
    end-to-end.
    """

    per_beat_diagrams: PerBeatDiagramsConfig = Field(
        default_factory=PerBeatDiagramsConfig
    )
    diagram_qa: DiagramQAConfig = Field(default_factory=DiagramQAConfig)
    beat_narration: BeatNarrationConfig = Field(default_factory=BeatNarrationConfig)
    length_enforcer: LengthEnforcerConfig = Field(default_factory=LengthEnforcerConfig)
    script_assembler: ScriptAssemblerConfig = Field(
        default_factory=ScriptAssemblerConfig
    )
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
            if cfg.llm.provider == "openai":
                cfg.llm.api_key = os.environ.get("OPENAI_API_KEY")
            elif cfg.llm.provider == "anthropic":
                cfg.llm.api_key = os.environ.get("ANTHROPIC_API_KEY")

        return cfg
