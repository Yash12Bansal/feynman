"""Prune spurious topics + re-title the Deep Feedforward Networks extraction.

The anchor extractor over-segmented Goodfellow ch6: cross-chapter references
(3.10, 3.22, 5.9) and equation numbers (6.11, 6.47) became spurious "topics",
and several real sections got sentence-fragment titles. This:
  - drops the 5 spurious topics everywhere they're referenced,
  - re-stitches the NEXT chain + cleans prereqs,
  - keeps only diagrams/questions referenced by surviving topics,
  - scrubs every topic-keyed chapter structure (topic_ids, lesson_plans,
    lesson_narrations, concept_visual_index, board_snapshots, segments),
  - re-derives real section titles for the survivors via one LLM call.

The chapter_manifest is NOT edited here — it's rebuilt cleanly afterwards by
`regen-audio` from the pruned assembled_chapter_script (cached audio reused).

Run:  poetry run python clean_deep_feedforward.py
Then: regen-audio --skip-neo4j ; DETACH DELETE subgraph ; load-extraction
"""

from __future__ import annotations

import json
import re

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

from lecture_pipeline_v2.config import PipelineConfig  # noqa: E402
from lecture_pipeline_v2.llm.factory import create_llm_provider  # noqa: E402

EXTRACTION = "out/deep-feedforward-networks/extraction.json"
PRUNE_SECTIONS = {"3.10", "3.22", "5.9", "6.11", "6.47"}


def _clip(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip()[:320]


def _scrub(obj, pruned: set[str]):
    """Drop pruned topic ids from a topic-keyed dict or a list of ids/objects."""
    if isinstance(obj, dict):
        return {k: v for k, v in obj.items() if k not in pruned}
    if isinstance(obj, list):
        return [
            x
            for x in obj
            if not (isinstance(x, str) and x in pruned)
            and not (isinstance(x, dict) and x.get("topic_id") in pruned)
        ]
    return obj


def main() -> None:
    d = json.load(open(EXTRACTION))
    topics = d["topics"]
    pruned_ids = {
        t["topic_id"] for t in topics if t.get("section_number") in PRUNE_SECTIONS
    }
    kept = [t for t in topics if t["topic_id"] not in pruned_ids]
    print(f"PRUNE {len(pruned_ids)}: {sorted(s for s in PRUNE_SECTIONS)}")
    print(f"keep {len(kept)} topics (was {len(topics)})")

    # 1. Re-derive titles for the survivors (one LLM call).
    lines = [
        f'- id "{t["topic_id"].split(":")[-1]}" (section {t.get("section_number")}): {_clip(t.get("orig_book_content"))}'
        for t in kept
    ]
    user = (
        "Below are sections of the 'Deep Feedforward Networks' chapter of "
        "Goodfellow's Deep Learning. Each line: id, section number, opening of "
        "the section text. The text may contain a running header 'CHAPTER 6. "
        "DEEP FEEDFORWARD NETWORKS', page numbers, equation labels, or algorithm "
        "pseudocode — IGNORE those. Return the REAL, concise section heading for "
        "each (e.g. 'Gradient-Based Learning', 'Computational Graphs', 'Chain "
        "Rule of Calculus', 'Rectified Linear Units and Their Generalizations'). "
        "For a genuine mid-section continuation with no heading, give a short, "
        "accurate descriptive title.\n\n"
        + "\n".join(lines)
        + "\n\nReturn ONLY a JSON object mapping each id to its title."
    )
    system = (
        "You extract clean, faithful section titles from messy textbook text. "
        "Concise headings, never sentences."
    )
    llm = create_llm_provider(PipelineConfig.load().llm)
    resp = llm.generate_json(system, user)
    titles = json.loads(
        re.sub(r"^```(?:json)?|```$", "", resp.content.strip(), flags=re.M).strip()
    )
    retitled = 0
    for t in kept:
        new = titles.get(t["topic_id"].split(":")[-1])
        if new and new.strip():
            t["topic_name"] = new.strip()
            retitled += 1
    print(f"re-titled {retitled}/{len(kept)}")

    # 2. Re-stitch NEXT (kept order) + clean prereqs.
    for i, t in enumerate(kept):
        t["next_topic_id"] = kept[i + 1]["topic_id"] if i + 1 < len(kept) else None
        t["prereq_topic_ids"] = [
            p for p in (t.get("prereq_topic_ids") or []) if p not in pruned_ids
        ]

    # 3. Keep only diagrams/questions referenced by surviving topics.
    kd: set[str] = set()
    kq: set[str] = set()
    for t in kept:
        kd.update(t.get("has_diagram_ids") or [])
        kq.update(t.get("has_question_ids") or [])
    diagrams = [dg for dg in d["diagrams"] if dg["diagram_id"] in kd]
    questions = [q for q in d["questions"] if q["question_id"] in kq]
    print(
        f"diagrams {len(d['diagrams'])}->{len(diagrams)} | "
        f"questions {len(d['questions'])}->{len(questions)}"
    )

    # 4. Scrub every topic-keyed chapter structure (manifest rebuilt separately).
    ch = d["chapters"][0]
    for field in (
        "topic_ids",
        "lesson_plans",
        "lesson_narrations",
        "concept_visual_index",
        "board_snapshots",
    ):
        if field in ch and ch[field] is not None:
            ch[field] = _scrub(ch[field], pruned_ids)
    acs = ch.get("assembled_chapter_script") or {}
    if acs.get("segments"):
        before = len(acs["segments"])
        acs["segments"] = _scrub(acs["segments"], pruned_ids)
        print(f"segments {before}->{len(acs['segments'])}")
    print(f"chapter.topic_ids -> {len(ch.get('topic_ids') or [])}")

    d["topics"], d["diagrams"], d["questions"] = kept, diagrams, questions

    # 5. Safety: no surviving reference to a pruned id outside the inert manifest.
    leftover = sum(
        json.dumps(d[k]).count(pid)
        for k in ("topics", "diagrams", "questions")
        for pid in pruned_ids
    )
    print(f"dangling pruned-id refs in topics/diagrams/questions: {leftover} (want 0)")

    json.dump(d, open(EXTRACTION, "w"), ensure_ascii=False, indent=2)
    print("saved", EXTRACTION)


if __name__ == "__main__":
    main()
