# TODO(DEADCODE): file unused in active pipelines (precompute-gen / lecture-playback / ask-feynman). See docs/engineering/13-redundant-code-audit.md Group 1. Safe to delete.
# """FastAPI router for the diagram-generation testbed.

# Mounted at `/api/diagtest/*` from `feynman.api.router`. All endpoints are
# testbed-only — no auth, in-memory state. Suitable for the single-user
# experimentation loop, not for production traffic.
# """

# from __future__ import annotations

# import json
# import traceback
# import uuid
# from collections import OrderedDict
# from pathlib import Path
# from typing import Any

# import structlog
# from fastapi import APIRouter, HTTPException
# from pydantic import BaseModel, Field

# from feynman.experiments.diagram_lab.annotations.injector import (
#     AnnotationRequest,
#     AnnotationResponse,
#     inject_annotation,
# )
# from feynman.experiments.diagram_lab.strategies.base import (
#     StrategyDescriptor,
#     StrategyResult,
# )
# from feynman.experiments.diagram_lab.strategies.registry import (
#     all_strategies,
#     get_strategy,
# )

# logger = structlog.get_logger()

# router = APIRouter()

# # ── In-memory run history (testbed-only) ──────────────────

# _HISTORY_MAX = 50
# _history: OrderedDict[str, dict[str, Any]] = OrderedDict()


# def _record(run_id: str, entry: dict[str, Any]) -> None:
#     _history[run_id] = entry
#     while len(_history) > _HISTORY_MAX:
#         _history.popitem(last=False)


# # ── Maths prompt library ─────────────────────────────────

# _LIBRARY_PATH = Path(__file__).parent / "prompts" / "maths_library.json"


# def _load_library() -> dict[str, Any]:
#     return json.loads(_LIBRARY_PATH.read_text(encoding="utf-8"))


# # ── Request / response models ─────────────────────────────


# class RunRequest(BaseModel):
#     strategy_id: str
#     model: str | None = None
#     prompt: str
#     options: dict[str, Any] | None = None
#     label: str | None = Field(default=None, description="Optional human label for history.")


# class RunResponse(BaseModel):
#     run_id: str
#     result: StrategyResult


# class HistoryEntry(BaseModel):
#     run_id: str
#     strategy_id: str
#     model: str
#     prompt: str
#     label: str | None
#     total_ms: float
#     element_count: int
#     success: bool
#     error: str | None = None


# # ── Endpoints ─────────────────────────────────────────────


# @router.get("/strategies", response_model=list[StrategyDescriptor])
# async def list_strategies() -> list[StrategyDescriptor]:
#     """Plugin discovery — the frontend uses this to build the strategy picker and options form."""
#     return [s.descriptor() for s in all_strategies()]


# @router.get("/maths-library")
# async def maths_library() -> dict[str, Any]:
#     """Curated IGCSE / class 9-12 maths prompts to seed experimentation."""
#     return _load_library()


# @router.post("/run", response_model=RunResponse)
# async def run_strategy(req: RunRequest) -> RunResponse:
#     if not req.prompt.strip():
#         raise HTTPException(status_code=400, detail="prompt must not be empty.")

#     try:
#         strategy = get_strategy(req.strategy_id)
#     except KeyError as exc:
#         raise HTTPException(status_code=404, detail=str(exc)) from exc

#     avail = strategy.availability()
#     if not avail.available:
#         raise HTTPException(
#             status_code=503,
#             detail=f"Strategy '{req.strategy_id}' unavailable: {avail.reason}",
#         )

#     model = req.model or strategy.default_model
#     if model not in strategy.supports_models and not model.startswith("claude-"):
#         logger.warning(
#             "diagtest.unsupported_model",
#             strategy=req.strategy_id,
#             model=model,
#             supported=strategy.supports_models,
#         )

#     try:
#         options = strategy.parse_options(req.options)
#     except Exception as exc:
#         raise HTTPException(status_code=400, detail=f"Invalid options: {exc}") from exc

#     run_id = uuid.uuid4().hex[:10]
#     logger.info(
#         "diagtest.run.start",
#         run_id=run_id,
#         strategy=req.strategy_id,
#         model=model,
#         prompt=req.prompt[:80],
#     )

#     try:
#         result = await strategy.generate(req.prompt, model, options)
#     except Exception as exc:
#         tb = traceback.format_exc()
#         logger.exception("diagtest.run.error", run_id=run_id, strategy=req.strategy_id)
#         _record(
#             run_id,
#             {
#                 "run_id": run_id,
#                 "strategy_id": req.strategy_id,
#                 "model": model,
#                 "prompt": req.prompt,
#                 "label": req.label,
#                 "total_ms": 0,
#                 "element_count": 0,
#                 "success": False,
#                 "error": f"{exc}\n\n{tb[-1000:]}",
#             },
#         )
#         raise HTTPException(status_code=500, detail=str(exc)) from exc

#     _record(
#         run_id,
#         {
#             "run_id": run_id,
#             "strategy_id": req.strategy_id,
#             "model": result.model_used,
#             "prompt": req.prompt,
#             "label": req.label,
#             "total_ms": result.timing.total_ms,
#             "element_count": result.metadata.get("element_count", 0),
#             "success": True,
#             "result": result.model_dump(),
#         },
#     )
#     return RunResponse(run_id=run_id, result=result)


# @router.get("/history", response_model=list[HistoryEntry])
# async def history() -> list[HistoryEntry]:
#     return [
#         HistoryEntry(
#             run_id=e["run_id"],
#             strategy_id=e["strategy_id"],
#             model=e["model"],
#             prompt=e["prompt"],
#             label=e.get("label"),
#             total_ms=e["total_ms"],
#             element_count=e["element_count"],
#             success=e["success"],
#             error=e.get("error"),
#         )
#         for e in reversed(_history.values())
#     ]


# @router.get("/history/{run_id}")
# async def history_entry(run_id: str) -> dict[str, Any]:
#     if run_id not in _history:
#         raise HTTPException(status_code=404, detail="run not found")
#     return _history[run_id]


# @router.post("/annotate", response_model=AnnotationResponse)
# async def annotate(req: AnnotationRequest) -> AnnotationResponse:
#     if not req.intent.strip():
#         raise HTTPException(status_code=400, detail="intent must not be empty.")
#     try:
#         return await inject_annotation(req)
#     except Exception as exc:
#         logger.exception("diagtest.annotate.error")
#         raise HTTPException(status_code=500, detail=str(exc)) from exc
