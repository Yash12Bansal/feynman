"""FastAPI application factory."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from feynman.api.router import router
from feynman.common.logging import setup_logging
from feynman.config import settings

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application startup and shutdown."""
    setup_logging(settings.log_level)
    logger.info("feynman.starting", environment=settings.environment)
    yield
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
