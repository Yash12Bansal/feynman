"""End-to-end GRADUATE-MODE ingest of one chapter.

Touches no existing pipeline code. The only "switch" is the single
`enable_graduate_mode()` call below — after it, the stock pipeline runs exactly
as normal, but the planner/judge/chapter prompts are the graduate versions.

Usage:
    poetry run python ingest_graduate.py                 # full end-to-end
    poetry run python ingest_graduate.py --skip-tts      # author only (fast QA pass)
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

# ── THE one-line switch ───────────────────────────────────────────────────
from lecture_pipeline_v2.grad_mode import enable_graduate_mode  # noqa: E402

enable_graduate_mode()
# ──────────────────────────────────────────────────────────────────────────

from lecture_pipeline_v2.config import PipelineConfig  # noqa: E402
from lecture_pipeline_v2.pipeline import CurriculumPipelineV2  # noqa: E402

SOURCE_PDF = "/Users/yashbansal/Downloads/Deep+Learning+Ian+Goodfellow.pdf"
SLICE_PDF = "deep_feedforward_ch6.pdf"
SUBJECT = "deep_learning"
TITLE = "Deep Feedforward Networks"
# Physical pages 185–243 (0-based 184..242); page 244 is already Chapter 7.
PAGE_FROM_0BASED = 184
PAGE_TO_0BASED = 242
OUT_DIR = Path("out/deep-feedforward-networks")


def _slice_chapter() -> int:
    import fitz

    src = fitz.open(SOURCE_PDF)
    out = fitz.open()
    out.insert_pdf(src, from_page=PAGE_FROM_0BASED, to_page=PAGE_TO_0BASED)
    out.save(SLICE_PDF)
    return out.page_count


async def main() -> None:
    flags = set(sys.argv[1:])
    pages = _slice_chapter()
    print(f"GRADUATE MODE on. Sliced {pages} pages -> {SLICE_PDF}")

    cfg = PipelineConfig.load()
    print(f"LLM: {cfg.llm.provider} ({cfg.llm.model})  subject={SUBJECT}")
    pipeline = CurriculumPipelineV2(cfg)

    def on_stage(stage: str, detail: str) -> None:
        print(f"  [{stage}] {detail}", flush=True)

    report = await pipeline.run(
        SLICE_PDF,
        SUBJECT,
        single_chapter_title=TITLE,
        skip_tts="--skip-tts" in flags,
        skip_questions="--skip-questions" in flags,
        skip_neo4j="--skip-neo4j" in flags,
        on_stage=on_stage,
    )

    print("\n" + report.summary())
    for w in report.warnings:
        print(f"  warning: {w}")

    if report.extraction:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        path = OUT_DIR / "extraction.json"
        report.extraction.save(path)
        print(f"\nExtraction saved: {path}")


if __name__ == "__main__":
    asyncio.run(main())
