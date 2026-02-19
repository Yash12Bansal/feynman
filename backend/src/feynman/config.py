"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
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

    # LiveKit
    livekit_url: str = "ws://localhost:7880"
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "devsecret"

    # Speech Providers
    deepgram_api_key: str = ""
    cartesia_api_key: str = ""

    # Database
    database_url: str = "postgresql+asyncpg://feynman:feynman@localhost:5432/feynman"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    @property
    def is_dev(self) -> bool:
        return self.environment == "development"


settings = Settings()
