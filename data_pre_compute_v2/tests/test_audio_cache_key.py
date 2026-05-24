"""Audio cache-key tests — Phase H cleanup.

Audio synthesis is expensive enough that we cache MP3s on disk. The cache key
USED to be `{topic_id}_{role}_{text_index}.mp3` with no content hash, which
silently reused stale audio when the underlying TTS text changed (e.g., the
doc-19 lesson narration replaced the legacy beat-narration for the same
topic). The fix in `audio_pipeline.py` includes a SHA-256 prefix of the text
in the filename. These tests pin that behavior.
"""

from __future__ import annotations

from lecture_pipeline_v2.curriculum.media.audio_pipeline import _audio_file_name


def test_cache_key_includes_content_hash_for_distinct_texts() -> None:
    """Same (topic, role, index) with DIFFERENT text → different filenames.

    Without this, a re-run that produces new narration would reuse the old
    audio file because the cache check is `if file_path.exists()`.
    """
    a = _audio_file_name(
        topic_id="topic:physics:relativity:47_1",
        role="chapter",
        text_index=0,
        text="Yesterday's legacy narration.",
        ext="mp3",
    )
    b = _audio_file_name(
        topic_id="topic:physics:relativity:47_1",
        role="chapter",
        text_index=0,
        text="Today's doc-19 narration is genuinely different.",
        ext="mp3",
    )
    assert a != b
    # Filenames must differ ONLY in the hash segment.
    assert a.startswith("topic_physics_relativity_47_1_chapter_000_")
    assert b.startswith("topic_physics_relativity_47_1_chapter_000_")
    assert a.endswith(".mp3")
    assert b.endswith(".mp3")


def test_cache_key_stable_for_identical_text() -> None:
    """Same text + position → same filename across calls.

    Legitimate re-runs of an unchanged extraction.json must hit the existing
    audio cache (otherwise we'd re-synthesize on every run for no reason).
    """
    text = "An honest narration sentence."
    a = _audio_file_name(
        topic_id="topic:physics:relativity:47_1",
        role="chapter",
        text_index=5,
        text=text,
        ext="mp3",
    )
    b = _audio_file_name(
        topic_id="topic:physics:relativity:47_1",
        role="chapter",
        text_index=5,
        text=text,
        ext="mp3",
    )
    assert a == b


def test_cache_key_topic_id_colons_replaced_with_underscores() -> None:
    """topic_id like `topic:physics:relativity:47_1` becomes filesystem-safe."""
    name = _audio_file_name(
        topic_id="topic:physics:relativity:47_1",
        role="chapter",
        text_index=0,
        text="anything",
        ext="mp3",
    )
    assert ":" not in name
    assert name.startswith("topic_physics_relativity_47_1_")


def test_cache_key_hash_length_is_10_hex_chars() -> None:
    """The hash segment is the 10-char prefix of SHA-256 (40 bits — collision
    probability for ~1000 fragments is ~5e-10)."""
    name = _audio_file_name(
        topic_id="t",
        role="chapter",
        text_index=0,
        text="anything",
        ext="mp3",
    )
    # Format: t_chapter_000_<10 hex chars>.mp3
    parts = name.rsplit(".", 1)[0].split("_")
    hash_segment = parts[-1]
    assert len(hash_segment) == 10
    assert all(c in "0123456789abcdef" for c in hash_segment)
