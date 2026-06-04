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
import re
from pathlib import Path
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from neo4j import AsyncGraphDatabase

from lecture_pipeline_v2.config import PipelineConfig
from lecture_pipeline_v2.tts.chunker import TextFragment, split_script

cfg = PipelineConfig.load()
artifacts_base = Path(cfg.artifacts.base_dir).resolve()
static_dir = Path(__file__).parent / "preview_static"

app = FastAPI(title="Lecture Player")
# /lecture-artifacts/ namespace avoids colliding with the live LiveKit backend's /artifacts/
# when both servers are running simultaneously behind the Vite dev proxy.
app.mount(
    "/lecture-artifacts", StaticFiles(directory=str(artifacts_base)), name="artifacts"
)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


_TOPIC_START_RE = re.compile(r"<<TOPIC_START:([^>]+)>>")


def _chunk_narration_by_topic(narration_text: str) -> dict[str, list[str]]:
    """Re-chunk Chapter.narration_text into {topic_id: [text fragments]}.

    The audio_pipeline at ingest time chunked the SAME narration string and
    rendered one MP3 per TextFragment per topic, in order. Re-running the
    same chunker on the same string gives us the same fragments back. We
    pair each fragment with its corresponding AudioEvent at request time so
    the frontend can render a live transcript without re-ingesting.
    """
    if not narration_text:
        return {}
    matches = list(_TOPIC_START_RE.finditer(narration_text))
    if not matches:
        return {}
    out: dict[str, list[str]] = {}
    for i, m in enumerate(matches):
        tid = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(narration_text)
        segment = narration_text[start:end]
        try:
            fragments = split_script(segment)
        except Exception:
            # Defensive: if the chunker rejects the segment for any reason,
            # leave no transcript for this topic rather than failing the API.
            continue
        out[tid] = [
            f.text.strip()
            for f in fragments
            if isinstance(f, TextFragment) and f.text.strip()
        ]
    return out


def _attach_transcript(
    events: list[dict], texts_by_topic: dict[str, list[str]]
) -> list[dict]:
    """Walk manifest events; attach `.text` to each AudioEvent from the
    matching topic's re-chunked text fragments, in order.
    """
    if not texts_by_topic:
        return events
    current_topic: str | None = None
    text_idx = 0
    out: list[dict] = []
    for ev in events:
        ev_type = ev.get("type")
        if ev_type == "topic_start":
            current_topic = ev.get("topic_id")
            text_idx = 0
        elif ev_type == "audio" and current_topic:
            texts = texts_by_topic.get(current_topic, [])
            if 0 <= text_idx < len(texts):
                ev = {**ev, "text": texts[text_idx]}
                text_idx += 1
        out.append(ev)
    return out


def rewrite_url(url: str | None) -> str | None:
    """file://./artifacts/... or file:///abs/... → /lecture-artifacts/... so the browser can fetch."""
    if not url:
        return url
    if url.startswith("file://./artifacts/"):
        return "/lecture-artifacts/" + url[len("file://./artifacts/") :]
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
        cfg.neo4j.uri,
        auth=(cfg.neo4j.username, cfg.neo4j.password),
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
        cfg.neo4j.uri,
        auth=(cfg.neo4j.username, cfg.neo4j.password),
    )
    try:
        async with driver.session(database=cfg.neo4j.database) as session:
            result = await session.run(
                "MATCH (c:Chapter {chapter_id: $id}) "
                "RETURN c.title AS title, c.chapter_index AS idx, "
                "       c.chapter_manifest AS manifest, "
                "       c.board_snapshots AS board_snapshots, "
                "       c.narration_text AS narration_text",
                {"id": chapter_id},
            )
            record = await result.single()
            if not record:
                raise HTTPException(404, f"Chapter not found: {chapter_id}")

            manifest_raw = record["manifest"]
            if not manifest_raw:
                raise HTTPException(
                    409, "Chapter has no chapter_manifest yet (TTS not run)"
                )
            manifest = (
                json.loads(manifest_raw)
                if isinstance(manifest_raw, str)
                else manifest_raw
            )
            events = manifest.get("events", [])
            snapshots_raw = record["board_snapshots"]
            board_snapshots = (
                json.loads(snapshots_raw)
                if isinstance(snapshots_raw, str) and snapshots_raw
                else (snapshots_raw or [])
            )

            diagram_ids = sorted(
                {e["diagram_id"] for e in events if e.get("type") == "show_diagram"}
            )
            diagrams: dict = {}
            if diagram_ids:
                result = await session.run(
                    "MATCH (d:Diagram) WHERE d.diagram_id IN $ids "
                    "RETURN d.diagram_id AS id, d.description AS desc, "
                    "       d.fallback_image_url AS url, "
                    "       d.render_data AS render_data, "
                    "       d.template_concept_id AS template_concept_id, "
                    "       d.template_params AS template_params",
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
                    template_concept_id = r["template_concept_id"]
                    tp_raw = r["template_params"]
                    template_params = (
                        json.loads(tp_raw) if isinstance(tp_raw, str) else tp_raw
                    )
                    # For a canonical-template diagram the frontend builds the
                    # spec from the registry; force spec=None so its
                    # `d.spec ?? buildTemplateSpec(...)` falls through (an empty
                    # {} render_data would otherwise shadow the template).
                    if template_concept_id:
                        spec = None
                    diagrams[r["id"]] = {
                        "url": rewrite_url(r["url"]),
                        "description": r["desc"] or "",
                        "spec": spec,
                        "template_concept_id": template_concept_id,
                        "template_params": template_params,
                    }

            topic_ids = sorted(
                {e["topic_id"] for e in events if e.get("type") == "topic_start"}
            )
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

    # Live transcript: re-chunk narration_text and attach `text` to each
    # AudioEvent so the frontend can render the currently-spoken sentence.
    texts_by_topic = _chunk_narration_by_topic(record["narration_text"] or "")
    events_with_text = _attach_transcript(events, texts_by_topic)

    rewritten_events = []
    for ev in events_with_text:
        if ev.get("type") == "audio":
            rewritten_events.append({**ev, "url": rewrite_url(ev["url"])})
        else:
            rewritten_events.append(ev)

    return JSONResponse(
        {
            "chapter_id": chapter_id,
            "title": record["title"],
            "chapter_index": record["idx"],
            "events": rewritten_events,
            "diagrams": diagrams,
            "topics": topics,
            "board_snapshots": board_snapshots,
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    print(f"\n  Lecture Player → http://{args.host}:{args.port}\n")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
