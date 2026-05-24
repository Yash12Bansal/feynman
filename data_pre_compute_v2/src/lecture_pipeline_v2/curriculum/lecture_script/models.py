from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChapterScript:
    """Result of one chapter's script-writing pass. Consumed by TTS layer.

    Built (post-Phase-4e) from ScriptAssembler's assembled_chapter_script dict
    via `ChapterScript(**ch.assembled_chapter_script)`. Pre-4e: built by
    ScriptWriter directly.
    """

    chapter_id: str
    segments: list[dict]
