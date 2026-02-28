"""FastAPI application factory."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from feynman.api.router import router
from feynman.common.logging import setup_logging
from feynman.config import settings
from feynman.db.base import Base
from feynman.db.engine import create_engine, create_session_factory
from feynman.redis.client import create_redis_client
from feynman.session.manager import SessionManager

# Import models so they register with Base.metadata
from feynman.session.models import SessionModel as _SessionModel  # noqa: F401

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application startup and shutdown."""
    setup_logging(settings.log_level)
    logger.info("feynman.starting", environment=settings.environment)

    engine = create_engine()
    db_factory = create_session_factory(engine)
    redis = create_redis_client()

    # Dev: auto-create tables. Production uses Alembic migrations.
    if settings.is_dev:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    app.state.engine = engine
    app.state.db_factory = db_factory
    app.state.redis = redis
    app.state.session_manager = SessionManager(db_factory, redis)

    yield

    await redis.aclose()
    await engine.dispose()
    logger.info("feynman.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Feynman",
        description="AI teaching agent for school classrooms",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router, prefix="/api")

    return app


app = create_app()
