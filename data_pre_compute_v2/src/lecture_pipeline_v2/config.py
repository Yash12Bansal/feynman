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


class PipelineConfig(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    pdf: PDFConfig = Field(default_factory=PDFConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
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
