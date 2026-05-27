"""Dump a single Chapter (and its Topics + Diagrams + Questions) from Neo4j
back into a CurriculumExtractionResult JSON file that `load-extraction` can
re-hydrate from.

Use case: when an `ingest-book` run populates Neo4j but doesn't leave a
per-chapter extraction file on disk (e.g., the runaway full-book ingest
that wrote only the last chapter into out/extraction.json). Without these
files, a teammate cannot pull the repo and `load-extraction` to get the
chapters into their local Neo4j.

Usage:
    poetry run python tools/dump_chapter_extraction.py chapter:physics:friction
    # → writes out/extraction_physics_friction.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from neo4j import GraphDatabase

from lecture_pipeline_v2.config import PipelineConfig
from lecture_pipeline_v2.curriculum.models import (
    Chapter,
    CurriculumExtractionResult,
    Diagram,
    ExtractionSource,
    Manifest,
    Question,
    Topic,
)


def _parse_json_str(value: object) -> object:
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def _topic_from_record(rec: dict) -> Topic:
    book_examples_raw = _parse_json_str(rec.get("book_examples")) or []
    standalone_manifest_raw = _parse_json_str(rec.get("standalone_manifest")) or {}
    return Topic(
        topic_id=rec["topic_id"],
        chapter_id=rec["chapter_id"],
        section_number=rec.get("section_number") or "",
        within_chapter_order=int(rec.get("within_chapter_order") or 0),
        topic_name=rec.get("topic_name") or rec["topic_id"],
        orig_book_content=rec.get("orig_book_content") or "",
        our_understanding=rec.get("our_understanding") or "",
        examples=list(rec.get("examples") or []),
        book_examples=book_examples_raw,
        next_topic_id=rec.get("next_topic_id"),
        prereq_topic_ids=list(rec.get("prereq_topic_ids") or []),
        has_diagram_ids=list(rec.get("has_diagram_ids") or []),
        has_question_ids=list(rec.get("has_question_ids") or []),
        standalone_manifest=Manifest.model_validate(standalone_manifest_raw),
        standalone_narration_text=rec.get("standalone_narration_text") or "",
        embedding=list(rec.get("embedding") or []),
        needs_review=bool(rec.get("needs_review", False)),
        language=rec.get("language") or "en",
        version=int(rec.get("version") or 1),
    )


def _diagram_from_record(rec: dict) -> Diagram:
    return Diagram(
        diagram_id=rec["diagram_id"],
        renderer=rec.get("renderer") or "svg",
        render_data=_parse_json_str(rec.get("render_data")) or {},
        description=rec.get("description") or "",
        fallback_image_url=rec.get("fallback_image_url"),
        linked_topic_ids=list(rec.get("linked_topic_ids") or []),
        linked_beat_id=rec.get("linked_beat_id") or "",
        presentation_mode=rec.get("presentation_mode") or "overview",
        needs_review=bool(rec.get("needs_review", False)),
        version=int(rec.get("version") or 1),
    )


def _question_from_record(rec: dict) -> Question:
    return Question(
        question_id=rec["question_id"],
        q_text=rec.get("q_text") or "",
        q_audio_url=rec.get("q_audio_url"),
        q_diagram_id=rec.get("q_diagram_id"),
        answer=rec.get("answer") or "",
        answer_audio_url=rec.get("answer_audio_url"),
        options=list(rec.get("options") or []),
        type=rec.get("type") or "mcq",
        source=rec.get("source") or "book",
        solution_confidence=float(rec.get("solution_confidence") or 1.0),
        linked_topic_ids=list(rec.get("linked_topic_ids") or []),
        needs_review=bool(rec.get("needs_review", False)),
        language=rec.get("language") or "en",
        version=int(rec.get("version") or 1),
    )


def _chapter_from_record(rec: dict) -> Chapter:
    chapter_manifest_raw = _parse_json_str(rec.get("chapter_manifest")) or {}
    return Chapter(
        chapter_id=rec["chapter_id"],
        chapter_index=int(rec.get("chapter_index") or 0),
        title=rec.get("title") or "",
        summary=rec.get("summary") or "",
        page_start=int(rec.get("page_start") or 0),
        page_end=int(rec.get("page_end") or 0),
        topic_ids=list(rec.get("topic_ids") or []),
        chapter_manifest=Manifest.model_validate(chapter_manifest_raw),
        narration_text=rec.get("narration_text") or "",
        pages=_parse_json_str(rec.get("pages")) or [],
        board_snapshots=_parse_json_str(rec.get("board_snapshots")) or [],
        concept_visual_index=_parse_json_str(rec.get("concept_visual_index")) or {"entries": []},
        embedding=list(rec.get("embedding") or []),
        language=rec.get("language") or "en",
        version=int(rec.get("version") or 1),
    )


def dump_chapter(chapter_id: str, output_path: Path) -> CurriculumExtractionResult:
    cfg = PipelineConfig.load()
    driver = GraphDatabase.driver(cfg.neo4j.uri, auth=(cfg.neo4j.username, cfg.neo4j.password))
    try:
        with driver.session(database=cfg.neo4j.database) as s:
            ch_rec = s.run(
                "MATCH (c:Chapter {chapter_id: $cid}) RETURN c {.*} AS c",
                cid=chapter_id,
            ).single()
            if ch_rec is None:
                raise RuntimeError(f"Chapter not found in Neo4j: {chapter_id}")
            chapter = _chapter_from_record(ch_rec["c"])

            topic_recs = list(
                s.run(
                    "MATCH (c:Chapter {chapter_id: $cid})-[:CONTAINS]->(t:Topic) "
                    "RETURN t {.*} AS t ORDER BY t.within_chapter_order",
                    cid=chapter_id,
                )
            )
            topics = [_topic_from_record(r["t"]) for r in topic_recs]
            topic_ids_set = {t.topic_id for t in topics}

            diagram_recs = list(
                s.run(
                    "MATCH (t:Topic)-[:HAS_DIAGRAM]->(d:Diagram) "
                    "WHERE t.topic_id IN $tids "
                    "RETURN DISTINCT d {.*} AS d",
                    tids=list(topic_ids_set),
                )
            )
            diagrams = [_diagram_from_record(r["d"]) for r in diagram_recs]

            question_recs = list(
                s.run(
                    "MATCH (t:Topic)-[:HAS_QUESTION]->(q:Question) "
                    "WHERE t.topic_id IN $tids "
                    "RETURN DISTINCT q {.*} AS q",
                    tids=list(topic_ids_set),
                )
            )
            questions = [_question_from_record(r["q"]) for r in question_recs]
    finally:
        driver.close()

    result = CurriculumExtractionResult(
        subject="physics" if "physics" in chapter_id else "mathematics",
        textbook_title="H C Verma- Concepts of Physics 1"
        if "physics" in chapter_id
        else "NCERT Mathematics",
        source=ExtractionSource(
            textbook_title="H C Verma- Concepts of Physics 1"
            if "physics" in chapter_id
            else "NCERT Mathematics",
            extractor_model="reconstructed-from-neo4j",
        ),
        chapters=[chapter],
        topics=topics,
        diagrams=diagrams,
        questions=questions,
    )
    result.save(output_path)
    print(
        f"  saved {output_path}: "
        f"chapters=1 topics={len(topics)} diagrams={len(diagrams)} questions={len(questions)}"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("chapter_id", help="e.g. chapter:physics:friction")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON path. Defaults to out/extraction_<slug>.json",
    )
    args = parser.parse_args()

    if args.output is None:
        slug = args.chapter_id.replace("chapter:", "").replace(":", "_")
        args.output = Path(__file__).parent.parent / "out" / f"extraction_{slug}.json"

    try:
        dump_chapter(args.chapter_id, args.output)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
