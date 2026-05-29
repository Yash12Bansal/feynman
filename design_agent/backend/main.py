# TODO(DEADCODE): file unused in active pipelines (precompute-gen / lecture-playback / ask-feynman). See docs/engineering/13-redundant-code-audit.md Group 1. Safe to delete.
# """FastAPI server for the diagram generation agent."""

# from __future__ import annotations

# import asyncio
# import json
# import logging
# import os
# import re
# import uuid
# from datetime import datetime
# from typing import Any, Optional

# from dotenv import load_dotenv
# from fastapi import FastAPI, HTTPException
# from fastapi.middleware.cors import CORSMiddleware
# from pydantic import BaseModel

# from agent import DiagramAgent

# # ---------------------------------------------------------------------------
# # Bootstrap
# # ---------------------------------------------------------------------------

# load_dotenv()

# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# app = FastAPI(
#     title="Diagram Agent API",
#     description="AI-powered diagram generation from natural language prompts",
#     version="0.1.0",
# )

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=[
#         "http://localhost:3000",
#         "http://localhost:3001",
#         "http://127.0.0.1:3000",
#         "http://127.0.0.1:3001",
#     ],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# agent = DiagramAgent()

# # ---------------------------------------------------------------------------
# # Spec-file persistence
# # ---------------------------------------------------------------------------

# GENERATED_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "generated")
# os.makedirs(GENERATED_DIR, exist_ok=True)


# def _save_spec(spec_dict: dict, prompt: str) -> str:
#     title = spec_dict.get("title", "untitled")
#     slug = re.sub(r"[^a-zA-Z0-9]+", "_", title).strip("_").lower()[:50]
#     timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
#     filename = f"{timestamp}_{slug}.json"
#     filepath = os.path.join(GENERATED_DIR, filename)
#     with open(filepath, "w") as f:
#         json.dump({"prompt": prompt, "spec": spec_dict}, f, indent=2)
#     return filepath


# # ---------------------------------------------------------------------------
# # Job store — tracks in-progress generations with partial elements
# # ---------------------------------------------------------------------------

# # jobs[job_id] = {
# #     "status": "generating" | "done" | "error",
# #     "accumulated": str,           # raw text so far
# #     "elements": [dict, ...],      # parsed complete elements so far
# #     "partial_spec": dict | None,  # partial spec with title/desc/etc
# #     "final_spec": dict | None,    # validated final spec
# #     "error": str | None,
# # }
# jobs: dict[str, dict] = {}


# def _extract_elements_from_partial(text: str) -> tuple[dict, list[dict]]:
#     """Extract top-level fields and complete element objects from partial JSON."""
#     meta = {
#         "title": "",
#         "description": "",
#         "width": 900,
#         "height": 650,
#         "backgroundColor": "#ffffff",
#     }

#     def _str(pattern):
#         m = re.search(pattern, text)
#         return m.group(1) if m else None

#     meta["title"] = _str(r'"title"\s*:\s*"([^"]*)"') or ""
#     meta["description"] = _str(r'"description"\s*:\s*"([^"]*)"') or ""
#     w = _str(r'"width"\s*:\s*(\d+)')
#     if w:
#         meta["width"] = int(w)
#     h = _str(r'"height"\s*:\s*(\d+)')
#     if h:
#         meta["height"] = int(h)
#     meta["backgroundColor"] = _str(r'"backgroundColor"\s*:\s*"([^"]*)"') or "#ffffff"

#     def _extract_objects(section_name: str) -> list[dict]:
#         results = []
#         idx = text.find(f'"{section_name}"')
#         if idx == -1:
#             return results
#         arr_start = text.find("[", idx)
#         if arr_start == -1:
#             return results
#         sub = text[arr_start + 1 :]
#         depth = 0
#         start = -1
#         for i, ch in enumerate(sub):
#             if ch == "{":
#                 if depth == 0:
#                     start = i
#                 depth += 1
#             elif ch == "}":
#                 depth -= 1
#                 if depth == 0 and start != -1:
#                     try:
#                         results.append(json.loads(sub[start : i + 1]))
#                     except json.JSONDecodeError:
#                         pass
#                     start = -1
#             elif ch == "]" and depth == 0:
#                 break
#         return results

#     elements = _extract_objects("elements")
#     params = _extract_objects("parameters")

#     return {**meta, "elements": elements, "parameters": params}, elements


# async def _run_generation(job_id: str, prompt: str, model: str | None):
#     """Background task: stream from Claude, update job store progressively."""
#     job = jobs[job_id]
#     try:
#         async for chunk in agent.generate_stream(prompt, model=model):
#             job["accumulated"] += chunk
#             # Parse partial results
#             partial, elements = _extract_elements_from_partial(job["accumulated"])
#             if len(elements) > len(job["elements"]):
#                 job["elements"] = elements
#                 job["partial_spec"] = partial

#         # Generation done — validate
#         spec_dict = agent.parse_response(job["accumulated"])
#         try:
#             _save_spec(spec_dict, prompt)
#         except Exception:
#             pass
#         job["final_spec"] = spec_dict
#         job["status"] = "done"
#         logger.info(
#             "Job %s completed: %d elements", job_id, len(spec_dict.get("elements", []))
#         )

#     except Exception as e:
#         logger.exception("Job %s failed", job_id)
#         job["status"] = "error"
#         job["error"] = str(e)


# # ---------------------------------------------------------------------------
# # Request / response models
# # ---------------------------------------------------------------------------


# class GenerateRequest(BaseModel):
#     prompt: str
#     model: Optional[str] = None


# class JobStartResponse(BaseModel):
#     job_id: str


# class JobStatusResponse(BaseModel):
#     status: str  # "generating", "done", "error"
#     elements_count: int
#     partial_spec: Optional[dict[str, Any]] = None
#     final_spec: Optional[dict[str, Any]] = None
#     error: Optional[str] = None


# class HealthResponse(BaseModel):
#     status: str
#     model: str


# # ---------------------------------------------------------------------------
# # Routes
# # ---------------------------------------------------------------------------


# @app.get("/api/health", response_model=HealthResponse)
# async def health() -> HealthResponse:
#     return HealthResponse(status="ok", model=agent.default_model)


# @app.post("/api/generate/start", response_model=JobStartResponse)
# async def start_generation(req: GenerateRequest):
#     """Start a diagram generation job. Returns a job_id to poll."""
#     if not req.prompt.strip():
#         raise HTTPException(status_code=400, detail="Prompt must not be empty.")

#     job_id = str(uuid.uuid4())[:8]
#     jobs[job_id] = {
#         "status": "generating",
#         "accumulated": "",
#         "elements": [],
#         "partial_spec": None,
#         "final_spec": None,
#         "error": None,
#     }

#     # Fire and forget the generation task
#     asyncio.create_task(_run_generation(job_id, req.prompt, req.model))

#     logger.info("Started job %s for: %s", job_id, req.prompt[:80])
#     return JobStartResponse(job_id=job_id)


# @app.get("/api/generate/status/{job_id}", response_model=JobStatusResponse)
# async def get_job_status(job_id: str):
#     """Poll for job progress. Returns partial elements while generating."""
#     if job_id not in jobs:
#         raise HTTPException(status_code=404, detail="Job not found")

#     job = jobs[job_id]

#     resp = JobStatusResponse(
#         status=job["status"],
#         elements_count=len(job["elements"]),
#         error=job.get("error"),
#     )

#     if job["status"] == "done":
#         resp.final_spec = job["final_spec"]
#         # Also include partial for smooth transition
#         resp.partial_spec = job.get("partial_spec")
#     elif job["status"] == "generating" and job["partial_spec"]:
#         resp.partial_spec = job["partial_spec"]

#     return resp


# @app.delete("/api/generate/status/{job_id}")
# async def cleanup_job(job_id: str):
#     """Clean up a completed job from memory."""
#     jobs.pop(job_id, None)
#     return {"ok": True}


# # Keep the old synchronous endpoint as fallback
# @app.post("/api/generate")
# async def generate_diagram(req: GenerateRequest):
#     if not req.prompt.strip():
#         raise HTTPException(status_code=400, detail="Prompt must not be empty.")
#     try:
#         diagram_dict = await agent.generate(req.prompt, model=req.model)
#     except ValueError as exc:
#         raise HTTPException(status_code=502, detail=str(exc)) from exc
#     except Exception as exc:
#         logger.exception("Unexpected error during generation")
#         raise HTTPException(status_code=500, detail=str(exc)) from exc
#     try:
#         _save_spec(diagram_dict, req.prompt)
#     except Exception:
#         pass
#     return {"diagram": diagram_dict}


# @app.get("/api/generated")
# async def list_generated_specs() -> list[dict[str, str]]:
#     results: list[dict[str, str]] = []
#     for name in sorted(os.listdir(GENERATED_DIR), reverse=True):
#         if not name.endswith(".json"):
#             continue
#         filepath = os.path.join(GENERATED_DIR, name)
#         try:
#             with open(filepath) as f:
#                 data = json.load(f)
#             results.append(
#                 {
#                     "filename": name,
#                     "prompt": data.get("prompt", ""),
#                     "title": data.get("spec", {}).get("title", ""),
#                 }
#             )
#         except Exception:
#             pass
#     return results


# if __name__ == "__main__":
#     import uvicorn

#     uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
