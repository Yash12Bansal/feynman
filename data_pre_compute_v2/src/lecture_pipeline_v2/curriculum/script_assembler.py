# TODO(DEADCODE): file unused in active precompute generation — legacy use_lesson_pipeline=False stack (default is True; doc-19 stack supersedes). See docs/engineering/13-redundant-code-audit.md Group 3. Safe to delete.
# """Phase 4d — ScriptAssembler.

# Pure sync string composition. Groups `chapter.beat_narrations` by `topic_id`,
# orders by `chapter.lecture_plan.concept_sequence`, inserts `<<PAUSE:short>>`
# between beats inside a topic and `<<PAUSE:long>>` between topics. Emits a dict
# in the same shape `lecture_script.ChapterScript` uses today:

#   {
#       "chapter_id": "...",
#       "segments": [
#           {
#               "topic_id": "...",
#               "narration_chapter": "...",
#               "narration_standalone": "...",
#           },
#           ...
#       ],
#   }

# Phase 4d stores this dict on `Chapter.assembled_chapter_script`. Phase 4e flips
# `ScriptAssemblerConfig.use_for_playback=True`; the pipeline then reconstructs
# the `ChapterScript` dataclass at swap time and feeds it to `AudioPipeline`.

# The standalone narration is identical to the chapter narration in Phase 4d —
# beat narrations don't carry "this is a fresh standalone landing" context yet.
# Phase 4e can introduce a dedicated `narration_standalone` shaping pass if
# needed.
# """

# from __future__ import annotations

# import logging
# from typing import Any

# from ..config import ScriptAssemblerConfig
# from .beat_narration.models import BeatNarration
# from .models import Chapter, Topic

# logger = logging.getLogger(__name__)


# class ScriptAssembler:
#     def __init__(self, *, config: ScriptAssemblerConfig) -> None:
#         self.config = config
#         self._beat_pause = f"<<PAUSE:{config.pause_between_beats}>>"
#         self._topic_pause = f"<<PAUSE:{config.pause_between_topics}>>"

#     def assemble_chapter(
#         self,
#         *,
#         chapter: Chapter,
#         topics_by_id: dict[str, Topic],
#     ) -> dict[str, Any] | None:
#         lp = chapter.lecture_plan
#         if lp is None or not chapter.beat_narrations:
#             return None

#         by_topic: dict[str, list[BeatNarration]] = {}
#         for n in chapter.beat_narrations:
#             by_topic.setdefault(n.topic_id, []).append(n)
#         for tid in by_topic:
#             by_topic[tid].sort(key=lambda n: n.beat_index)

#         segments: list[dict[str, str]] = []
#         for topic_id in lp.concept_sequence:
#             topic = topics_by_id.get(topic_id)
#             beats = by_topic.get(topic_id, [])
#             if topic is None or not beats:
#                 continue
#             non_empty = [b.text.strip() for b in beats if b.text and b.text.strip()]
#             if not non_empty:
#                 continue
#             joined = self._beat_pause.join(non_empty)
#             segments.append(
#                 {
#                     "topic_id": topic_id,
#                     "narration_chapter": joined,
#                     "narration_standalone": joined,
#                 }
#             )

#         if not segments:
#             return None

#         return {
#             "chapter_id": chapter.chapter_id,
#             "segments": segments,
#         }
