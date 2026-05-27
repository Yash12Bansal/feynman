"""Classroom-feel playback server.

Reads the chapter manifest from Neo4j, serves the audio fragments + diagram
images as static files, and exposes a tiny HTML/JS player that walks the
manifest events: plays audio fragments in order, renders diagrams when
show_diagram events fire, inserts silences for pause events, and updates a
topic label when topic_start fires.

Usage:
    poetry install --extras preview
    poetry run python tools/preview_server.py
    # open http://localhost:8080
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from neo4j import AsyncGraphDatabase

from lecture_pipeline_v2.config import PipelineConfig

cfg = PipelineConfig.load()
artifacts_base = Path(cfg.artifacts.base_dir).resolve()
static_dir = Path(__file__).parent / "preview_static"

app = FastAPI(title="Lecture Player")
# /lecture-artifacts/ namespace avoids colliding with the live LiveKit backend's /artifacts/
# when both servers are running simultaneously behind the Vite dev proxy.
app.mount("/lecture-artifacts", StaticFiles(directory=str(artifacts_base)), name="artifacts")
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


def rewrite_url(url: str | None) -> str | None:
    """file://./artifacts/... or file:///abs/... → /lecture-artifacts/... so the browser can fetch."""
    if not url:
        return url
    if url.startswith("file://./artifacts/"):
        return "/lecture-artifacts/" + url[len("file://./artifacts/"):]
    if url.startswith("file://"):
        path = urlparse(url).path
        try:
            rel = Path(path).resolve().relative_to(artifacts_base)
            return f"/lecture-artifacts/{rel.as_posix()}"
        except ValueError:
            return url
    return url


@app.get("/")
async def root() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/lecture-api/chapters")
async def list_chapters() -> JSONResponse:
    driver = AsyncGraphDatabase.driver(
        cfg.neo4j.uri, auth=(cfg.neo4j.username, cfg.neo4j.password),
    )
    try:
        async with driver.session(database=cfg.neo4j.database) as session:
            result = await session.run(
                "MATCH (c:Chapter) "
                "RETURN c.chapter_id AS id, c.title AS title, c.chapter_index AS idx, "
                "       c.chapter_manifest IS NOT NULL AS has_manifest "
                "ORDER BY c.chapter_index"
            )
            chapters = [dict(r) async for r in result]
    finally:
        await driver.close()
    return JSONResponse(chapters)


@app.get("/lecture-api/chapter/{chapter_id:path}")
async def chapter_data(chapter_id: str) -> JSONResponse:
    driver = AsyncGraphDatabase.driver(
        cfg.neo4j.uri, auth=(cfg.neo4j.username, cfg.neo4j.password),
    )
    try:
        async with driver.session(database=cfg.neo4j.database) as session:
            result = await session.run(
                "MATCH (c:Chapter {chapter_id: $id}) "
                "RETURN c.title AS title, c.chapter_index AS idx, "
                "       c.chapter_manifest AS manifest, "
                "       c.board_snapshots AS board_snapshots",
                {"id": chapter_id},
            )
            record = await result.single()
            if not record:
                raise HTTPException(404, f"Chapter not found: {chapter_id}")

            manifest_raw = record["manifest"]
            if not manifest_raw:
                raise HTTPException(409, "Chapter has no chapter_manifest yet (TTS not run)")
            manifest = (
                json.loads(manifest_raw) if isinstance(manifest_raw, str) else manifest_raw
            )
            events = manifest.get("events", [])
            snapshots_raw = record["board_snapshots"]
            board_snapshots = (
                json.loads(snapshots_raw)
                if isinstance(snapshots_raw, str) and snapshots_raw
                else (snapshots_raw or [])
            )

            diagram_ids = sorted({
                e["diagram_id"] for e in events if e.get("type") == "show_diagram"
            })
            diagrams: dict = {}
            if diagram_ids:
                result = await session.run(
                    "MATCH (d:Diagram) WHERE d.diagram_id IN $ids "
                    "RETURN d.diagram_id AS id, d.description AS desc, "
                    "       d.fallback_image_url AS url, "
                    "       d.render_data AS render_data",
                    {"ids": diagram_ids},
                )
                async for r in result:
                    rd_raw = r["render_data"]
                    if isinstance(rd_raw, str):
                        try:
                            spec = json.loads(rd_raw)
                        except json.JSONDecodeError:
                            spec = None
                    else:
                        spec = rd_raw
                    diagrams[r["id"]] = {
                        "url": rewrite_url(r["url"]),
                        "description": r["desc"] or "",
                        "spec": spec,
                    }

            topic_ids = sorted({
                e["topic_id"] for e in events if e.get("type") == "topic_start"
            })
            topics: dict = {}
            if topic_ids:
                result = await session.run(
                    "MATCH (t:Topic) WHERE t.topic_id IN $ids "
                    "RETURN t.topic_id AS id, t.topic_name AS name, "
                    "       t.section_number AS section",
                    {"ids": topic_ids},
                )
                async for r in result:
                    topics[r["id"]] = {
                        "name": r["name"],
                        "section": r["section"],
                    }
    finally:
        await driver.close()

    rewritten_events = []
    for ev in events:
        if ev.get("type") == "audio":
            rewritten_events.append({**ev, "url": rewrite_url(ev["url"])})
        else:
            rewritten_events.append(ev)

    return JSONResponse({
        "chapter_id": chapter_id,
        "title": record["title"],
        "chapter_index": record["idx"],
        "events": rewritten_events,
        "diagrams": diagrams,
        "topics": topics,
        "board_snapshots": board_snapshots,
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    print(f"\n  Lecture Player → http://{args.host}:{args.port}\n")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
