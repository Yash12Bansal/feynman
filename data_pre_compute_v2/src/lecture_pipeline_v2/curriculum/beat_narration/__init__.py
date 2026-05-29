"""Phase 4d — per-beat narration.

`BeatNarrationWriter` turns each `TeachingBeat` (Phase 4b) into a marker-embedded
narration string, drawing role vocabulary from the active diagram's
`render_data["dictionary"]` (Phase 1). `LengthEnforcer` then trims the chapter
to its budget; `ScriptAssembler` (sibling module) stitches the per-beat
narrations into the `ChapterScript` shape `ScriptWriter` produces today.

Sidecar in Phase 4d — `ScriptAssembler.use_for_playback=False` by default;
ScriptWriter (Phase 8) still drives audio. Phase 4e flips the bit and removes
ScriptWriter.
"""

from .models import BeatNarration
# TODO(DEADCODE): BeatNarrationWriter/Report are legacy (use_lesson_pipeline=False stack). See docs/engineering/13-redundant-code-audit.md Group 3. Safe to delete.
# from .writer import BeatNarrationReport, BeatNarrationWriter

__all__ = ["BeatNarration"]
