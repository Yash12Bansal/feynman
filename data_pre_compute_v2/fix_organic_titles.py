"""One-off: repair garbled `topic_name`s in an extraction whose PDF had a
decorative running header that leaked into section titles.

Derives the real book section heading for each topic from its
`orig_book_content` via one cheap LLM call, rewrites `topic_name`, saves.
Does NOT touch ids, content, narration, diagrams, audio, or manifests.

Usage: poetry run python fix_organic_titles.py out/organic-chemistry/extraction.json
"""

from __future__ import annotations

import json
import re
import sys

from dotenv import find_dotenv, load_dotenv

# Load ANTHROPIC_API_KEY etc. from .env, exactly as the CLI does, before any
# provider is constructed.
load_dotenv(find_dotenv(usecwd=True))

from lecture_pipeline_v2.config import PipelineConfig  # noqa: E402
from lecture_pipeline_v2.llm.factory import create_llm_provider  # noqa: E402

EXTRACTION = sys.argv[1] if len(sys.argv) > 1 else "out/organic-chemistry/extraction.json"


def clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip()[:320]


def main() -> None:
    d = json.load(open(EXTRACTION))
    topics = d["topics"]

    lines = []
    for t in topics:
        short = t["topic_id"].split(":")[-1]
        sn = t.get("section_number") or short
        lines.append(f'- id "{short}" (section {sn}): {clean(t.get("orig_book_content"))}')

    user = (
        "Below are the sections of an IGCSE Chemistry 'Organic chemistry' "
        "chapter. Each line is one section: its id, its section number, and the "
        "opening of its textbook text. The text contains a decorative running "
        "header reading 'O r g a n i c  c h e m i s t r y' (letters spaced out) "
        "and a stray page number right after the section number — IGNORE both. "
        "Extract the REAL, concise section heading for each, faithful to the "
        "book (e.g. 'Petroleum: a fossil fuel', 'Refining petroleum', "
        "'Cracking hydrocarbons', 'The alkanes', 'The alkenes').\n\n"
        + "\n".join(lines)
        + '\n\nReturn ONLY a JSON object mapping each id to its title, e.g. '
        '{"17_1": "Petroleum: a fossil fuel"}.'
    )
    system = (
        "You extract clean, faithful section titles from messy textbook OCR "
        "text. Concise — a heading, not a sentence."
    )

    cfg = PipelineConfig.load()
    llm = create_llm_provider(cfg.llm)
    resp = llm.generate_json(system, user)
    text = re.sub(r"^```(?:json)?|```$", "", resp.content.strip(), flags=re.M).strip()
    titles = json.loads(text)
    print("Derived titles:")
    print(json.dumps(titles, indent=2, ensure_ascii=False))

    applied = 0
    for t in topics:
        short = t["topic_id"].split(":")[-1]
        new = titles.get(short)
        if new and new.strip():
            t["topic_name"] = new.strip()
            applied += 1
    print(f"\nApplied {applied}/{len(topics)} topic_name updates.")

    json.dump(d, open(EXTRACTION, "w"), ensure_ascii=False, indent=2)
    print(f"Saved {EXTRACTION}")


if __name__ == "__main__":
    main()
