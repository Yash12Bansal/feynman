"""SQLAlchemy async engine factory."""

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from feynman.config import settings


def create_engine() -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        echo=settings.is_dev,
        pool_pre_ping=True,
        # Keep each process's pool SMALL. On Cloud Run many instances run in
        # parallel; the SQLAlchemy default (pool_size=5 + max_overflow=10 = 15
        # per process) x dozens of instances would blow past Cloud SQL's
        # connection limit and crash with "too many connections". 5/process x
        # a capped --max-instances stays well under the limit. See DEPLOY.md.
        pool_size=3,
        max_overflow=2,
        pool_timeout=10,
        pool_recycle=1800,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)
