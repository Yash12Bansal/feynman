"""SQLAlchemy async engine factory."""

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from feynman.config import settings


def create_engine() -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        echo=settings.is_dev,
        pool_pre_ping=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)
