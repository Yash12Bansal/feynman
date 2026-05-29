# TODO(DEADCODE): tests parked/dead modules (Group 1/2/3); see docs/engineering/13-redundant-code-audit.md. Safe to delete.
# """Tests for the Phase 4 ``tts_node`` stream-tap helper.

# The helper :func:`feynman.livekit.worker.strip_action_tags` wraps the LLM
# text iterable that ``Agent.tts_node`` feeds into the TTS engine. These
# tests verify the contract:

# - Every action tag in the stream is handed to ``on_tag`` in stream order.
# - The cleaned text reaching TTS has all tags removed.
# - A tag straddling chunk boundaries is reassembled before dispatch.
# - Stream end with no orphan does not invoke ``on_tag`` again.
# """

# from __future__ import annotations

# from collections.abc import AsyncGenerator

# import pytest

# from feynman.agent.action_tag_parser import ActionTag
# # TODO(DEADCODE): module tests interactive live-teaching worker internals (parked). See docs/engineering/13-redundant-code-audit.md Group 2. Safe to delete.
# import pytest as _deadcode_pytest
# _deadcode_pytest.skip(
#     "interactive worker tests (parked) — see docs/engineering/13-redundant-code-audit.md Group 2",
#     allow_module_level=True,
# )
# from feynman.livekit.worker import strip_action_tags


# async def _aiter(chunks: list[str]) -> AsyncGenerator[str]:
#     for c in chunks:
#         yield c


# async def _collect(
#     chunks: list[str],
# ) -> tuple[str, list[ActionTag]]:
#     seen_tags: list[ActionTag] = []
#     out = ""
#     async for clean in strip_action_tags(_aiter(chunks), seen_tags.append):
#         out += clean
#     return out, seen_tags


# @pytest.mark.asyncio
# async def test_strip_tag_in_single_chunk() -> None:
#     out, tags = await _collect(['Look at <highlight target="x"/> the side.'])
#     assert out == "Look at  the side."
#     assert [(t.verb, t.attrs.get("target")) for t in tags] == [("highlight", "x")]


# @pytest.mark.asyncio
# async def test_strip_tag_split_across_chunks() -> None:
#     out, tags = await _collect(["Look at <high", 'light target="x"/> the side.'])
#     assert out == "Look at  the side."
#     assert len(tags) == 1
#     assert tags[0].verb == "highlight"
#     assert tags[0].attrs["target"] == "x"


# @pytest.mark.asyncio
# async def test_two_tags_in_stream_dispatched_in_order() -> None:
#     out, tags = await _collect(
#         [
#             'First <highlight target="a"/> then ',
#             '<pulse target="b"/> done.',
#         ]
#     )
#     assert "highlight" not in out and "pulse" not in out
#     assert [(t.verb, t.attrs["target"]) for t in tags] == [
#         ("highlight", "a"),
#         ("pulse", "b"),
#     ]


# @pytest.mark.asyncio
# async def test_tag_at_stream_end_with_no_trailing_text() -> None:
#     out, tags = await _collect(['Look at <highlight target="x"/>'])
#     assert out == "Look at "
#     assert [(t.verb, t.attrs["target"]) for t in tags] == [("highlight", "x")]


# @pytest.mark.asyncio
# async def test_empty_stream_yields_nothing() -> None:
#     out, tags = await _collect([])
#     assert out == ""
#     assert tags == []


# @pytest.mark.asyncio
# async def test_no_tags_passes_through_verbatim() -> None:
#     chunks = ["The hypotenuse ", "is the longest ", "side of the triangle."]
#     out, tags = await _collect(chunks)
#     assert out == "The hypotenuse is the longest side of the triangle."
#     assert tags == []


# @pytest.mark.asyncio
# async def test_orphan_tag_at_stream_end_is_dropped_silently() -> None:
#     """LLM stops mid-tag (turn interrupted). Orphan fragment is dropped;
#     no spurious dispatch; voice flow ends cleanly."""
#     out, tags = await _collect(["Look at <high"])
#     assert out == "Look at "
#     assert tags == []
