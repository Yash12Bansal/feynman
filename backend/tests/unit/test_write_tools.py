# TODO(DEADCODE): tests parked/dead modules (Group 1/2/3); see docs/engineering/13-redundant-code-audit.md. Safe to delete.
# """Tests for the notebook write-tools added in split-board Phase 5.

# Each tool builds a typed instruction, calls `_publish_visual`, and therefore
# publishes a JSON message over the visuals data channel. These tests mock the
# RunContext and assert the published payload's shape + panel routing.
# """

# from __future__ import annotations

# import json
# from unittest.mock import AsyncMock, MagicMock

# import pytest

# from feynman.agent.board import BoardManager
# from feynman.agent.session_audit import SessionAudit
# from feynman.agent.tools import (
#     new_page,
#     strikethrough,
#     write_answer,
#     write_equation,
#     write_section,
#     write_step,
#     write_text,
# )


# def _make_mock_ctx() -> MagicMock:
#     """Build a RunContext mock sufficient for `_publish_visual`."""
#     ctx = MagicMock()
#     ctx.wait_for_playout = AsyncMock()
#     ctx.session.room_io.room.local_participant.publish_data = AsyncMock()

#     userdata = MagicMock()
#     userdata.board_manager = BoardManager()
#     userdata.audit = SessionAudit()
#     userdata.current_concept = None
#     userdata.current_concept_index = 0
#     userdata.lesson_plan = None
#     ctx.userdata = userdata
#     return ctx


# def _published(ctx: MagicMock) -> dict:
#     """Return the payload of the single published instruction."""
#     publish = ctx.session.room_io.room.local_participant.publish_data
#     assert publish.call_count == 1, (
#         f"expected exactly one publish, got {publish.call_count}"
#     )
#     call = publish.call_args
#     raw = call.args[0] if call.args else call.kwargs.get("data")
#     return json.loads(raw)


# @pytest.mark.asyncio
# async def test_write_equation_publishes_notebook_instruction() -> None:
#     ctx = _make_mock_ctx()
#     result = await write_equation(
#         ctx,
#         latex="F = m a",
#         label="Newton's 2nd",
#         align_group="solve-for-a",
#         indent=1,
#     )
#     payload = _published(ctx)
#     assert payload["type"] == "write_equation"
#     assert payload["panel"] == "notebook"
#     assert payload["latex"] == "F = m a"
#     assert payload["label"] == "Newton's 2nd"
#     assert payload["align_group"] == "solve-for-a"
#     assert payload["indent"] == 1
#     assert "Wrote equation" in result


# @pytest.mark.asyncio
# async def test_write_step_publishes_notebook_instruction() -> None:
#     ctx = _make_mock_ctx()
#     await write_step(ctx, text="Solve for a", number=2, indent=1)
#     payload = _published(ctx)
#     assert payload["type"] == "write_step"
#     assert payload["panel"] == "notebook"
#     assert payload["text"] == "Solve for a"
#     assert payload["number"] == 2
#     assert payload["indent"] == 1


# @pytest.mark.asyncio
# async def test_write_step_number_zero_serializes_as_null() -> None:
#     ctx = _make_mock_ctx()
#     await write_step(ctx, text="An unnumbered step")
#     payload = _published(ctx)
#     # number=0 is treated as "unnumbered" — instruction stores None, excluded from JSON.
#     assert "number" not in payload or payload.get("number") is None


# @pytest.mark.asyncio
# async def test_write_text_default_style_publishes_notebook_instruction() -> None:
#     ctx = _make_mock_ctx()
#     await write_text(ctx, text="Remember this")
#     payload = _published(ctx)
#     assert payload["type"] == "write_text"
#     assert payload["panel"] == "notebook"
#     assert payload["style"] == "default"
#     assert payload["text"] == "Remember this"


# @pytest.mark.asyncio
# async def test_write_text_key_point_style_flows_through() -> None:
#     ctx = _make_mock_ctx()
#     await write_text(ctx, text="Key idea", style="key_point")
#     payload = _published(ctx)
#     assert payload["style"] == "key_point"


# @pytest.mark.asyncio
# async def test_write_section_publishes_notebook_instruction() -> None:
#     ctx = _make_mock_ctx()
#     await write_section(ctx, title="Newton's Second Law")
#     payload = _published(ctx)
#     assert payload["type"] == "write_section"
#     assert payload["panel"] == "notebook"
#     assert payload["title"] == "Newton's Second Law"


# @pytest.mark.asyncio
# async def test_write_answer_with_latex() -> None:
#     ctx = _make_mock_ctx()
#     await write_answer(ctx, latex="a = 5\\,\\text{m/s}^2")
#     payload = _published(ctx)
#     assert payload["type"] == "write_answer"
#     assert payload["panel"] == "notebook"
#     assert payload["latex"] == "a = 5\\,\\text{m/s}^2"


# @pytest.mark.asyncio
# async def test_write_answer_with_text() -> None:
#     ctx = _make_mock_ctx()
#     await write_answer(ctx, text="pH = 7.0")
#     payload = _published(ctx)
#     assert payload["text"] == "pH = 7.0"


# @pytest.mark.asyncio
# async def test_write_answer_requires_latex_or_text() -> None:
#     ctx = _make_mock_ctx()
#     with pytest.raises(ValueError, match="requires latex or text"):
#         await write_answer(ctx)


# @pytest.mark.asyncio
# async def test_strikethrough_publishes_notebook_instruction() -> None:
#     ctx = _make_mock_ctx()
#     await strikethrough(ctx, target_id="eq-3")
#     payload = _published(ctx)
#     assert payload["type"] == "strikethrough"
#     assert payload["panel"] == "notebook"
#     assert payload["target_id"] == "eq-3"
#     # strikethrough is immediate — does not wait for playout.
#     ctx.wait_for_playout.assert_not_called()


# @pytest.mark.asyncio
# async def test_new_page_publishes_notebook_instruction() -> None:
#     ctx = _make_mock_ctx()
#     await new_page(ctx)
#     payload = _published(ctx)
#     assert payload["type"] == "new_page"
#     assert payload["panel"] == "notebook"
#     # Default carry_forward_ids is the empty list.
#     assert payload.get("carry_forward_ids", []) == []
#     # new_page is immediate — does not wait for playout.
#     ctx.wait_for_playout.assert_not_called()


# @pytest.mark.asyncio
# async def test_new_page_with_carry_forward_publishes_ids() -> None:
#     ctx = _make_mock_ctx()
#     await new_page(ctx, carry_forward_ids=["eq-1", "eq-2"])
#     payload = _published(ctx)
#     assert payload["type"] == "new_page"
#     assert payload["panel"] == "notebook"
#     assert payload["carry_forward_ids"] == ["eq-1", "eq-2"]
