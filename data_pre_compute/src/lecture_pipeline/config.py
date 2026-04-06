"""Configuration management for the lecture pipeline."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class LLMConfig(BaseModel):
    provider: Literal["openai", "anthropic"] = "openai"
    model: str = "gpt-4o"
    base_url: str | None = None
    temperature: float = 0.3
    max_tokens: int = 4096
    api_key: str | None = None


class PDFConfig(BaseModel):
    ocr_threshold: int = 50
    image_dpi: int = 200
    ocr_language: str = "eng"


class OutputConfig(BaseModel):
    output_dir: str = "./output"


class Neo4jConfig(BaseModel):
    uri: str = "bolt://localhost:7687"
    username: str = "neo4j"
    password: str = "password"
    database: str = "neo4j"
    embedding_dimensions: int = 1536
    embedding_model: str = "text-embedding-3-small"
    embedding_batch_size: int = 100


class SalienceConfig(BaseModel):
    alpha: float = Field(default=0.6, description="Weight for static salience")
    beta: float = Field(default=0.4, description="Weight for structural salience")


class PipelineConfig(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    pdf: PDFConfig = Field(default_factory=PDFConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    neo4j: Neo4jConfig = Field(default_factory=Neo4jConfig)
    salience: SalienceConfig = Field(default_factory=SalienceConfig)

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
        """Load config from file, falling back to defaults.

        Resolution order: explicit path > ./config.yaml > defaults.
        API keys are read from env vars if not set in config:
          OPENAI_API_KEY, ANTHROPIC_API_KEY
        """
        if config_path:
            cfg = cls.from_yaml(config_path)
        elif Path("config.yaml").exists():
            cfg = cls.from_yaml("config.yaml")
        else:
            cfg = cls()

        # Resolve API key from environment if not provided
        if cfg.llm.api_key is None:
            if cfg.llm.provider == "openai":
                cfg.llm.api_key = os.environ.get("OPENAI_API_KEY")
            elif cfg.llm.provider == "anthropic":
                cfg.llm.api_key = os.environ.get("ANTHROPIC_API_KEY")

        return cfg
