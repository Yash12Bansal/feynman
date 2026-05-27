"""Build the Concept-to-Visual Index (Idea 2) for one chapter.

The index is one row per (diagram, dictionary element) across every diagram
linked to the chapter. We pull `role` + `semantic` straight from each
diagram's `render_data.dictionary` (which is what the design_agent populates
when it authors the diagram). `linked_beat_id` rides along from the parent
diagram so beat-anchored consumers can scope queries.

Pure function — no IO. The caller hands us the chapter's diagrams; we
return the index. Called from `audio_pipeline.py` at the same lifecycle
point that produces board_snapshots so the two artifacts stay in sync.
"""

from __future__ import annotations

from typing import Any

from lecture_pipeline_v2.curriculum.models import (
    ConceptVisualIndex,
    Diagram,
    VisualTermEntry,
)


def build_concept_visual_index(diagrams: list[Diagram]) -> ConceptVisualIndex:
    """Build the index from a chapter's diagrams.

    Skips diagrams without a `render_data.dictionary`, and dictionary entries
    where both `role` and `semantic` are empty (nothing to index on). Sort is
    stable on (diagram_id, element_id) so re-running the pipeline produces a
    byte-identical index when the diagrams haven't changed — cheap diffing.
    """
    entries: list[VisualTermEntry] = []
    for diagram in sorted(diagrams, key=lambda d: d.diagram_id):
        dictionary = _extract_dictionary(diagram)
        if not dictionary:
            continue
        linked_beat_id = getattr(diagram, "linked_beat_id", "") or ""
        for element_id, entry in sorted(dictionary.items()):
            if not isinstance(entry, dict):
                continue
            role = (entry.get("role") or "").strip()
            semantic = (entry.get("semantic") or "").strip()
            if not role and not semantic:
                continue
            entries.append(
                VisualTermEntry(
                    diagram_id=diagram.diagram_id,
                    element_id=element_id,
                    role=role,
                    semantic=semantic,
                    linked_beat_id=linked_beat_id,
                )
            )
    return ConceptVisualIndex(entries=entries)


def _extract_dictionary(diagram: Diagram) -> dict[str, Any]:
    render_data = getattr(diagram, "render_data", None)
    if not isinstance(render_data, dict):
        return {}
    dictionary = render_data.get("dictionary")
    return dictionary if isinstance(dictionary, dict) else {}
