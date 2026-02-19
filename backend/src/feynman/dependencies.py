"""Shared FastAPI dependencies."""

from feynman.config import Settings, settings


async def get_settings() -> Settings:
    return settings
