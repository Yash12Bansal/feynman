"""Reproduce the lecture script-writer call in isolation so we can see what
Claude actually returns, identify why segments are dropped, and iterate on
the prompt without re-running the full pipeline.

Reads chapter + topics + diagrams from Neo4j, builds the user prompt the
real pipeline would, calls Claude, prints the raw response, and runs the
validator to show exactly what gets filtered.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase

from lecture_pipeline_v2.config import PipelineConfig
from lecture_pipeline_v2.curriculum.lecture_script.script_writer import (
    SCRIPT_SYSTEM_PROMPT,
    ScriptWriter,
)
from lecture_pipeline_v2.curriculum.models import (
    Chapter,
    Diagram,
    DiagramRenderer,
    Topic,
)
from lecture_pipeline_v2.llm.factory import create_llm_provider


load_dotenv(Path(__file__).parent.parent.parent / ".env")


async def load_state(cfg: PipelineConfig, chapter_id: str):
    driver = AsyncGraphDatabase.driver(
        cfg.neo4j.uri, auth=(cfg.neo4j.username, cfg.neo4j.password),
    )
    try:
        async with driver.session(database=cfg.neo4j.database) as s:
            r = await s.run(
                "MATCH (c:Chapter {chapter_id: $id}) "
                "RETURN c.chapter_id AS id, c.chapter_index AS idx, c.title AS title, "
                "       c.summary AS summary, c.page_start AS ps, c.page_end AS pe, "
                "       c.topic_ids AS tids",
                {"id": chapter_id},
            )
            row = await r.single()
            if not row:
                raise SystemExit(f"chapter not found: {chapter_id}")
            chapter = Chapter(
                chapter_id=row["id"],
                chapter_index=row["idx"],
                title=row["title"],
                summary=row["summary"] or "",
                page_start=row["ps"],
                page_end=row["pe"],
                topic_ids=row["tids"] or [],
            )

            r = await s.run(
                "MATCH (c:Chapter {chapter_id: $id})-[:CONTAINS]->(t:Topic) "
                "RETURN t.topic_id AS id, t.chapter_id AS cid, t.section_number AS sec, "
                "       t.within_chapter_order AS ord, t.topic_name AS name, "
                "       t.orig_book_content AS orig, t.our_understanding AS our, "
                "       t.examples AS ex, t.has_diagram_ids AS dids "
                "ORDER BY ord",
                {"id": chapter_id},
            )
            topics: list[Topic] = []
            async for row in r:
                topics.append(Topic(
                    topic_id=row["id"], chapter_id=row["cid"], section_number=row["sec"],
                    within_chapter_order=row["ord"], topic_name=row["name"],
                    orig_book_content=row["orig"] or "",
                    our_understanding=row["our"] or "",
                    examples=row["ex"] or [],
                    has_diagram_ids=row["dids"] or [],
                ))

            r = await s.run(
                "MATCH (t:Topic)-[:HAS_DIAGRAM]->(d:Diagram) "
                "WHERE t.chapter_id = $id "
                "RETURN d.diagram_id AS id, d.renderer AS rnd, d.render_data AS rd, "
                "       d.description AS desc, d.linked_topic_ids AS topics",
                {"id": chapter_id},
            )
            diagrams: list[Diagram] = []
            async for row in r:
                rd = row["rd"]
                if isinstance(rd, str):
                    try:
                        rd = json.loads(rd)
                    except json.JSONDecodeError:
                        rd = {}
                diagrams.append(Diagram(
                    diagram_id=row["id"],
                    renderer=DiagramRenderer(row["rnd"] or "svg"),
                    render_data=rd or {},
                    description=row["desc"] or "",
                    linked_topic_ids=row["topics"] or [],
                ))
    finally:
        await driver.close()

    return chapter, topics, diagrams


def group_diagrams(diagrams: list[Diagram]) -> dict[str, list[Diagram]]:
    out: dict[str, list[Diagram]] = {}
    for d in diagrams:
        for tid in d.linked_topic_ids:
            out.setdefault(tid, []).append(d)
    return out


async def main() -> None:
    cfg = PipelineConfig.load()
    # Make sure key is in env so AnthropicProvider picks it up.
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY not in env (load_dotenv should have set it)")

    chapter_id = "chapter:physics:newtons_laws_of_motion"
    chapter, topics, diagrams = await load_state(cfg, chapter_id)
    diagrams_by_topic = group_diagrams(diagrams)
    print(f"Loaded chapter '{chapter.title}'")
    print(f"  topics: {len(topics)}")
    print(f"  diagrams: {len(diagrams)} ({sum(1 for d in diagrams_by_topic.values() for _ in d)} associations)")
    print(f"  chapter.summary length: {len(chapter.summary)}")
    print()

    llm = create_llm_provider(cfg.llm)
    sw = ScriptWriter(llm)

    user_prompt = sw._build_user_prompt(chapter, topics, diagrams_by_topic)
    print(f"SYSTEM_PROMPT length: {len(SCRIPT_SYSTEM_PROMPT)} chars (≈{len(SCRIPT_SYSTEM_PROMPT) // 4} tokens)")
    print(f"USER_PROMPT length:   {len(user_prompt)} chars (≈{len(user_prompt) // 4} tokens)")
    print()

    print("=== calling Claude ===")
    response = llm.generate_json(SCRIPT_SYSTEM_PROMPT, user_prompt)
    raw = response.content
    print(f"response length: {len(raw)} chars (≈{len(raw) // 4} tokens out)")
    if response.usage:
        print(f"usage: in={response.usage.get('input_tokens')} out={response.usage.get('output_tokens')}")
    print()

    # Save raw response for inspection
    raw_path = Path("/tmp/script_writer_raw.json")
    raw_path.write_text(raw)
    print(f"raw response saved → {raw_path}")
    print()

    print("=== first 800 chars of response ===")
    print(raw[:800])
    print()
    print("=== last 400 chars ===")
    print(raw[-400:])
    print()

    print("=== try parsing ===")
    try:
        data = json.loads(raw)
        print(f"  JSON valid ✓")
        segments = data.get("segments") or []
        print(f"  top-level segments: {len(segments)}")
        topic_ids = {t.topic_id for t in topics}
        for i, seg in enumerate(segments[:3]):
            tid = seg.get("topic_id") if isinstance(seg, dict) else "?"
            chap = (seg.get("narration_chapter") if isinstance(seg, dict) else "") or ""
            standalone = (seg.get("narration_standalone") if isinstance(seg, dict) else "") or ""
            tid_match = tid in topic_ids if tid else False
            print(f"  seg[{i}]: tid={tid!r} match={tid_match}  chap={len(chap.strip())} chars  standalone={len(standalone.strip())} chars")
    except json.JSONDecodeError as e:
        print(f"  JSON INVALID at pos {e.pos}: {e.msg}")


if __name__ == "__main__":
    asyncio.run(main())
