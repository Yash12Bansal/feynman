"""Stitch a chapter's audio fragments into one MP3 for offline listening.

Reads the Chapter.chapter_manifest from Neo4j, walks the event sequence,
and concatenates all referenced audio files via ffmpeg's concat demuxer.
PauseEvents are rendered as silent audio of the specified duration.
ShowDiagramEvent and TopicStartEvent are skipped (UI-only).

Usage:
    poetry run python tools/stitch_chapter_audio.py \\
        --chapter-id "chapter:physics:newton_s_laws_of_motion" \\
        --output /tmp/chapter5.mp3

Or by chapter_index:
    poetry run python tools/stitch_chapter_audio.py --chapter-index 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from neo4j import AsyncGraphDatabase

from lecture_pipeline_v2.config import PipelineConfig


def url_to_local_path(url: str, artifacts_base: Path) -> Path:
    """Convert manifest URLs back to local filesystem paths.

    Manifest URLs look like 'file://./artifacts/audio/.../foo.mp3'.
    We strip the prefix and resolve relative to the artifacts base.
    """
    parsed = urlparse(url)
    path = parsed.path or url
    if url.startswith("file://./"):
        rel = url[len("file://./"):]
        return (artifacts_base.parent / rel).resolve()
    if url.startswith("file://"):
        return Path(parsed.path).resolve()
    return Path(path).resolve()


def make_silence(duration_ms: int, sample_rate: int, out_dir: Path) -> Path:
    """Render a silent MP3 of the requested length."""
    secs = duration_ms / 1000.0
    out = out_dir / f"silence_{duration_ms}.mp3"
    if out.exists():
        return out
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"anullsrc=r={sample_rate}:cl=mono",
        "-t", f"{secs}",
        "-acodec", "libmp3lame", "-q:a", "5",
        str(out),
    ]
    subprocess.run(cmd, check=True)
    return out


def concat_with_ffmpeg(file_list: list[Path], output: Path) -> None:
    """Concatenate audio files using ffmpeg's concat demuxer."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for p in file_list:
            f.write(f"file '{p}'\n")
        list_path = f.name

    try:
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0",
            "-i", list_path,
            "-c", "copy",
            str(output),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            # codec copy fails when inputs have mismatched bitrates — re-encode
            cmd_reenc = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "concat", "-safe", "0",
                "-i", list_path,
                "-acodec", "libmp3lame", "-q:a", "4",
                str(output),
            ]
            subprocess.run(cmd_reenc, check=True)
    finally:
        Path(list_path).unlink(missing_ok=True)


async def fetch_chapter(
    cfg: PipelineConfig, chapter_id: str | None, chapter_index: int | None,
) -> dict:
    driver = AsyncGraphDatabase.driver(
        cfg.neo4j.uri, auth=(cfg.neo4j.username, cfg.neo4j.password),
    )
    try:
        async with driver.session(database=cfg.neo4j.database) as session:
            if chapter_id:
                query = (
                    "MATCH (c:Chapter {chapter_id: $cid}) "
                    "RETURN c.chapter_id AS id, c.title AS title, "
                    "       c.chapter_index AS idx, c.chapter_manifest AS manifest"
                )
                params = {"cid": chapter_id}
            else:
                query = (
                    "MATCH (c:Chapter {chapter_index: $idx}) "
                    "RETURN c.chapter_id AS id, c.title AS title, "
                    "       c.chapter_index AS idx, c.chapter_manifest AS manifest"
                )
                params = {"idx": chapter_index}
            result = await session.run(query, params)
            record = await result.single()
            if not record:
                raise SystemExit(f"Chapter not found.")
            return dict(record)
    finally:
        await driver.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--chapter-id")
    grp.add_argument("--chapter-index", type=int)
    ap.add_argument("--output", required=True, help="Output MP3 path")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found on PATH. brew install ffmpeg")

    cfg = PipelineConfig.load(args.config)

    record = asyncio.run(fetch_chapter(cfg, args.chapter_id, args.chapter_index))
    chapter_title = record["title"]
    chapter_idx = record["idx"]
    manifest_raw = record["manifest"]

    if manifest_raw is None:
        raise SystemExit(
            f"Chapter '{chapter_title}' has no chapter_manifest yet. "
            "Did the TTS phase run? Re-run ingest-book without --skip-tts."
        )

    manifest = (
        json.loads(manifest_raw) if isinstance(manifest_raw, str) else manifest_raw
    )
    events = manifest.get("events", [])
    print(f"Chapter {chapter_idx}: {chapter_title}")
    print(f"Events in manifest: {len(events)}")

    artifacts_base = Path(cfg.artifacts.base_dir).resolve()
    work_dir = Path(tempfile.mkdtemp(prefix="stitch_"))
    sample_rate = cfg.tts.sample_rate

    files: list[Path] = []
    audio_count = 0
    pause_count = 0
    diagram_cues = 0
    topic_marks = 0

    for ev in events:
        t = ev.get("type")
        if t == "audio":
            local = url_to_local_path(ev["url"], artifacts_base)
            if not local.exists():
                print(f"  WARN: missing audio file: {local}")
                continue
            files.append(local)
            audio_count += 1
        elif t == "pause":
            sil = make_silence(int(ev["duration_ms"]), sample_rate, work_dir)
            files.append(sil)
            pause_count += 1
        elif t == "show_diagram":
            diagram_cues += 1
        elif t == "topic_start":
            topic_marks += 1

    print(
        f"Inputs: {audio_count} audio fragments, {pause_count} silences "
        f"(skipped: {diagram_cues} diagram cues, {topic_marks} topic markers)"
    )

    if not files:
        raise SystemExit("Nothing to stitch — no usable audio fragments found.")

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Stitching {len(files)} pieces → {output_path}")
    concat_with_ffmpeg(files, output_path)
    shutil.rmtree(work_dir, ignore_errors=True)

    size_mb = output_path.stat().st_size / 1_000_000
    print(f"Done. {output_path.name} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
