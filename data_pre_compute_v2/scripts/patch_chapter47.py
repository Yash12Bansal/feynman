"""One-shot patch for `out/phaseH/extraction.json` (chapter 47).

The Phase H ingest produced a high-quality `extraction.json` but two bugs
made the lecture unplayable:

1. `LessonQualityGate.gate_one_topic` called `narrator.render(plan=plan)`
   WITHOUT a `diagram_id_resolver`, so the manifest's SHOW_DIAGRAM markers
   carry the planner's short ids (e.g. `two-frames`) while the actual
   diagrams are stored with the long UID (e.g.
   `diagram:physics:the_special_theory_of_relativity:47_1:two_frames`).
   The frontend can't resolve the short id → slide stuck on "loading".

2. Phase 5 `EnrichmentOrchestrator` ran (it's pre-doc-19) and produced 7
   legacy per-topic diagrams named after slugified topic titles
   (`the_principle_of_relativity`, etc.). These are dead artifacts — no
   manifest event references them — but they sit in `extraction.diagrams`
   alongside the 7 doc-19 diagrams (14 total) and bloat Neo4j.

Both root causes are fixed in code for FUTURE ingests. This script patches
the EXISTING extraction.json in place so we don't have to spend another
$10 on an LLM re-ingest. Idempotent: running it twice is a no-op.

After running this script, run:
    poetry run lecture-pipeline-v2 regen-audio out/phaseH/extraction.json \\
        --chapter "Special Theory of Relativity" --clean

That re-renders audio with the corrected manifest markers AND pushes the
updated extraction.json into Neo4j so the preview server picks it up.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Allow running this script directly: `python scripts/patch_chapter47.py`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lecture_pipeline_v2.curriculum.id_generator import generate_diagram_uid
from lecture_pipeline_v2.curriculum.models import CurriculumExtractionResult
from lecture_pipeline_v2.pipeline import _build_chapter_script_from_narrations


_SHOW_DIAGRAM_RE = re.compile(r"<<SHOW_DIAGRAM:([^>]+)>>")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "extraction_path",
        type=str,
        help="Path to extraction.json (e.g. out/phaseH/extraction.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing the file back.",
    )
    args = parser.parse_args()

    path = Path(args.extraction_path)
    if not path.exists():
        print(f"ERROR: {path} does not exist", file=sys.stderr)
        return 1

    extraction = CurriculumExtractionResult.load(str(path))

    rewrite_events = 0
    rewrite_markers = 0
    dropped_diagrams = 0

    for chapter in extraction.chapters:
        # Build the per-topic short → long mapping from every LessonPlan
        # in the chapter. Each plan's `topic_id` keys into its own short
        # → long table.
        per_topic_short_to_long: dict[str, dict[str, str]] = {}
        all_short_to_long: dict[str, str] = {}
        keep_long_ids: set[str] = set()

        for plan in chapter.lesson_plans:
            t_map: dict[str, str] = {}
            for req in plan.diagrams:
                long_id = generate_diagram_uid(plan.topic_id, req.diagram_id)
                t_map[req.diagram_id] = long_id
                # Manifest events don't carry topic_id, so we also build
                # a flat map for the manifest pass. Short ids are LLM-
                # chosen per topic, but in practice they're globally
                # unique within a chapter (diagram_id maps cleanly).
                all_short_to_long[req.diagram_id] = long_id
                keep_long_ids.add(long_id)
            per_topic_short_to_long[plan.topic_id] = t_map

        # 1. Rewrite SHOW_DIAGRAM markers in each lesson_narration.
        for nar in chapter.lesson_narrations:
            t_map = per_topic_short_to_long.get(nar.topic_id, {})

            def _replace(match: re.Match[str], _map: dict[str, str] = t_map) -> str:
                nonlocal rewrite_markers
                short = match.group(1)
                long = _map.get(short)
                if long is None or long == short:
                    return match.group(0)
                rewrite_markers += 1
                return f"<<SHOW_DIAGRAM:{long}>>"

            nar.full_text_with_markers = _SHOW_DIAGRAM_RE.sub(
                _replace, nar.full_text_with_markers
            )
            for seg in nar.segments:
                seg.text_with_markers = _SHOW_DIAGRAM_RE.sub(
                    _replace, seg.text_with_markers
                )
            # Refresh diagrams_referenced list from the rewritten text.
            referenced = []
            seen = set()
            for m in _SHOW_DIAGRAM_RE.finditer(nar.full_text_with_markers):
                d = m.group(1)
                if d not in seen:
                    seen.add(d)
                    referenced.append(d)
            nar.diagrams_referenced = referenced

        # 2. Rebuild assembled_chapter_script from the patched narrations.
        chapter.assembled_chapter_script = _build_chapter_script_from_narrations(
            chapter_id=chapter.chapter_id,
            narrations=list(chapter.lesson_narrations),
        )

        # 3. Walk chapter_manifest.events; rewrite any ShowDiagramEvent
        # whose diagram_id is a known short id.
        for event in chapter.chapter_manifest.events:
            ev_diagram_id = getattr(event, "diagram_id", None)
            if ev_diagram_id and ev_diagram_id in all_short_to_long:
                long = all_short_to_long[ev_diagram_id]
                # ManifestEvent is a Pydantic model — assignment works.
                event.diagram_id = long
                rewrite_events += 1

    # 4. Strip legacy diagrams: keep only those whose diagram_id appears in
    # ANY LessonPlan's resolved long-id set.
    keep_all_long_ids: set[str] = set()
    for chapter in extraction.chapters:
        for plan in chapter.lesson_plans:
            for req in plan.diagrams:
                keep_all_long_ids.add(
                    generate_diagram_uid(plan.topic_id, req.diagram_id)
                )

    original_diagram_count = len(extraction.diagrams)
    extraction.diagrams = [
        d for d in extraction.diagrams if d.diagram_id in keep_all_long_ids
    ]
    dropped_diagrams = original_diagram_count - len(extraction.diagrams)

    # 5. Also strip the legacy diagram_ids from each topic.has_diagram_ids.
    keep_set = {d.diagram_id for d in extraction.diagrams}
    for topic in extraction.topics:
        topic.has_diagram_ids = [d for d in topic.has_diagram_ids if d in keep_set]

    # Summary.
    print("== patch_chapter47.py summary ==")
    print(f"  extraction: {path}")
    print(f"  manifest show_diagram events rewritten: {rewrite_events}")
    print(f"  narration SHOW_DIAGRAM markers rewritten: {rewrite_markers}")
    print(f"  diagrams dropped (legacy): {dropped_diagrams}")
    print(f"  diagrams remaining: {len(extraction.diagrams)}")

    if args.dry_run:
        print("\n  (dry-run: not writing)")
        return 0

    extraction.save(str(path))
    print(f"\n  extraction saved → {path}")
    print("\nNext step:")
    print(
        f"  poetry run lecture-pipeline-v2 regen-audio {path} "
        f'--chapter "Special Theory of Relativity" --clean'
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
