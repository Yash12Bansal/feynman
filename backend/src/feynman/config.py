"""Application configuration via environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env at the project root (two levels up from this file: src/feynman/config.py → project root)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    environment: str = "development"
    log_level: str = "DEBUG"
    backend_port: int = 8000
    frontend_url: str = "http://localhost:5173"

    # LLM Providers
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # Ollama / Local Models
    ollama_base_url: str = "http://localhost:11434"
    design_agent_provider: str = "anthropic"  # "anthropic" or "ollama"
    design_agent_model: str = ""  # model name for ollama (e.g. "qwen2.5-vl:7b")

    # LiveKit
    livekit_url: str = "ws://localhost:7880"
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "devsecret"

    # Speech Providers
    deepgram_api_key: str = ""
    cartesia_api_key: str = ""

    # Database
    database_url: str = "postgresql+asyncpg://feynman:feynman@localhost:5433/feynman"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Neo4j (curriculum graph)
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    neo4j_database: str = "neo4j"

    @property
    def is_dev(self) -> bool:
        return self.environment == "development"


settings = Settings()
