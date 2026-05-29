"""Root API router — aggregates all sub-routers."""

from fastapi import APIRouter

from feynman.api.health import router as health_router
from feynman.api.sessions import router as sessions_router
from feynman.api.students import router as students_router

# TODO(DEADCODE): diagram_lab is a dev-only testbed, unused in active pipelines (precompute-gen / lecture-playback / ask-feynman). See docs/engineering/13-redundant-code-audit.md Group 1. Safe to delete.
# from feynman.experiments.diagram_lab.router import router as diagtest_router

router = APIRouter()
router.include_router(health_router, tags=["health"])
router.include_router(sessions_router, prefix="/sessions", tags=["sessions"])
router.include_router(students_router, prefix="/students", tags=["students"])
# TODO(DEADCODE): dev-only diagtest router. See docs/engineering/13-redundant-code-audit.md Group 1. Safe to delete.
# router.include_router(diagtest_router, prefix="/diagtest", tags=["diagtest"])
