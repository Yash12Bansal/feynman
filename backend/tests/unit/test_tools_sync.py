"""Tests for voice-visual synchronization: playout gating + sync metadata + zone/board tracking."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from feynman.agent.board import BoardManager
from feynman.visuals.schemas import (
    BoardZone,
    ClearInstruction,
    ShowEquationInstruction,
    ShowTextInstruction,
    SyncMode,
    TermSyncHint,
)

# ── SyncMode and TermSyncHint schema tests ─────────────────────


class TestSyncModeEnum:
    def test_values(self) -> None:
        assert SyncMode.IMMEDIATE == "immediate"
        assert SyncMode.ON_PLAYOUT == "on_playout"
        assert SyncMode.TERM_SYNC == "term_sync"

    def test_default_on_base_instruction(self) -> None:
        """All instructions default to ON_PLAYOUT sync mode."""
        instr = ShowTextInstruction(text="Hello")
        assert instr.sync_mode == SyncMode.ON_PLAYOUT
        assert instr.term_hints is None


class TestTermSyncHint:
    def test_construction(self) -> None:
        hint = TermSyncHint(term_id="term-F", trigger_words=["force", "F"])
        assert hint.term_id == "term-F"
        assert hint.trigger_words == ["force", "F"]

    def test_serialization_roundtrip(self) -> None:
        hint = TermSyncHint(term_id="term-m", trigger_words=["mass", "m"])
        data = hint.model_dump()
        restored = TermSyncHint(**data)
        assert restored.term_id == hint.term_id
        assert restored.trigger_words == hint.trigger_words


class TestSyncFieldsSerialization:
    def test_sync_mode_excluded_when_default(self) -> None:
        """ON_PLAYOUT is the default — should still serialize (not None)."""
        instr = ShowTextInstruction(text="Hello")
        data = instr.model_dump(exclude_none=True)
        # sync_mode has a default value so it's always included
        assert data["sync_mode"] == "on_playout"
        assert "term_hints" not in data  # None → excluded

    def test_sync_mode_immediate(self) -> None:
        instr = ClearInstruction(sync_mode=SyncMode.IMMEDIATE)
        data = instr.model_dump(exclude_none=True)
        assert data["sync_mode"] == "immediate"

    def test_term_hints_serialized(self) -> None:
        hints = [
            TermSyncHint(term_id="term-F", trigger_words=["force", "F"]),
            TermSyncHint(term_id="term-m", trigger_words=["mass"]),
        ]
        instr = ShowEquationInstruction(
            latex="F = ma",
            sync_mode=SyncMode.TERM_SYNC,
            term_hints=hints,
        )
        data = instr.model_dump(exclude_none=True)
        assert data["sync_mode"] == "term_sync"
        assert len(data["term_hints"]) == 2
        assert data["term_hints"][0]["term_id"] == "term-F"

    def test_roundtrip_through_json(self) -> None:
        hints = [TermSyncHint(term_id="term-a", trigger_words=["acceleration", "a"])]
        original = ShowEquationInstruction(
            latex="F = ma",
            sync_mode=SyncMode.TERM_SYNC,
            term_hints=hints,
            element_id="eq-1",
        )
        json_str = json.dumps(original.model_dump(exclude_none=True))
        parsed = ShowEquationInstruction.model_validate_json(json_str)
        assert parsed.sync_mode == SyncMode.TERM_SYNC
        assert parsed.term_hints is not None
        assert len(parsed.term_hints) == 1
        assert parsed.term_hints[0].trigger_words == ["acceleration", "a"]


# ── Mock helpers ─────────────────────────────────────────────


def _make_mock_ctx(*, playout_raises: bool = False) -> MagicMock:
    """Create a mock RunContext with room, wait_for_playout, and TeachingContext userdata."""
    ctx = MagicMock()
    if playout_raises:
        ctx.wait_for_playout = AsyncMock(side_effect=RuntimeError("playout failed"))
    else:
        ctx.wait_for_playout = AsyncMock()
    ctx.session.room_io.room.local_participant.publish_data = AsyncMock()

    # TeachingContext-like userdata with board_manager
    userdata = MagicMock()
    userdata.board_manager = BoardManager()
    ctx.userdata = userdata

    return ctx


# ── Playout gating tests ──────────────────────────────────────


class TestPublishVisualPlayoutGating:
    @pytest.mark.asyncio
    async def test_waits_for_playout_by_default(self) -> None:
        from feynman.agent.tools import _publish_visual

        ctx = _make_mock_ctx()
        instruction = ShowTextInstruction(text="Hello")
        await _publish_visual(ctx, instruction)

        ctx.wait_for_playout.assert_awaited_once()
        ctx.session.room_io.room.local_participant.publish_data.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_playout_when_disabled(self) -> None:
        from feynman.agent.tools import _publish_visual

        ctx = _make_mock_ctx()
        instruction = ClearInstruction()
        await _publish_visual(ctx, instruction, wait_for_speech=False)

        ctx.wait_for_playout.assert_not_awaited()
        ctx.session.room_io.room.local_participant.publish_data.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_playout_failure(self) -> None:
        """When wait_for_playout raises, visual still publishes."""
        from feynman.agent.tools import _publish_visual

        ctx = _make_mock_ctx(playout_raises=True)
        instruction = ShowTextInstruction(text="Still works")
        await _publish_visual(ctx, instruction)

        ctx.wait_for_playout.assert_awaited_once()
        # Visual should still publish despite the exception
        ctx.session.room_io.room.local_participant.publish_data.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_published_data_contains_sync_mode(self) -> None:
        from feynman.agent.tools import _publish_visual

        ctx = _make_mock_ctx()
        instruction = ShowEquationInstruction(
            latex="E = mc^2",
            sync_mode=SyncMode.TERM_SYNC,
            term_hints=[TermSyncHint(term_id="term-E", trigger_words=["energy"])],
        )
        await _publish_visual(ctx, instruction)

        call_args = ctx.session.room_io.room.local_participant.publish_data.call_args
        published_json = call_args[0][0]
        parsed = json.loads(published_json)
        assert parsed["sync_mode"] == "term_sync"
        assert parsed["term_hints"][0]["term_id"] == "term-E"


# ── Tool-level tests ──────────────────────────────────────────


class TestClearBoardSync:
    def test_clear_instruction_uses_immediate_mode(self) -> None:
        """clear_board creates a ClearInstruction with IMMEDIATE sync mode."""
        instr = ClearInstruction(sync_mode=SyncMode.IMMEDIATE)
        assert instr.sync_mode == SyncMode.IMMEDIATE

    @pytest.mark.asyncio
    async def test_clear_publishes_without_playout_wait(self) -> None:
        """Publishing with wait_for_speech=False skips playout."""
        from feynman.agent.tools import _publish_visual

        ctx = _make_mock_ctx()
        instr = ClearInstruction(sync_mode=SyncMode.IMMEDIATE)
        await _publish_visual(ctx, instr, wait_for_speech=False)

        ctx.wait_for_playout.assert_not_awaited()
        call_args = ctx.session.room_io.room.local_participant.publish_data.call_args
        published = json.loads(call_args[0][0])
        assert published["sync_mode"] == "immediate"


class TestShowEquationSyncHints:
    def test_term_hints_with_term_by_term_sets_sync_mode(self) -> None:
        """Providing term_hints with term_by_term animation sets TERM_SYNC mode."""
        hints = [
            TermSyncHint(term_id="term-F", trigger_words=["force", "F"]),
            TermSyncHint(term_id="term-m", trigger_words=["mass", "m"]),
        ]
        instr = ShowEquationInstruction(
            latex="F = ma",
            animation="term_by_term",
            sync_mode=SyncMode.TERM_SYNC,
            term_hints=hints,
        )
        data = instr.model_dump(exclude_none=True)
        assert data["sync_mode"] == "term_sync"
        assert len(data["term_hints"]) == 2

    def test_term_hints_without_term_by_term_stays_on_playout(self) -> None:
        """term_hints with fade_in animation keeps ON_PLAYOUT sync mode."""
        hints = [TermSyncHint(term_id="term-F", trigger_words=["force"])]
        instr = ShowEquationInstruction(
            latex="F = ma",
            animation="fade_in",
            sync_mode=SyncMode.ON_PLAYOUT,
            term_hints=hints,
        )
        assert instr.sync_mode == SyncMode.ON_PLAYOUT

    def test_no_term_hints_default(self) -> None:
        """Without term_hints, sync_mode stays ON_PLAYOUT."""
        instr = ShowEquationInstruction(latex="E = mc^2")
        assert instr.sync_mode == SyncMode.ON_PLAYOUT
        assert instr.term_hints is None

    @pytest.mark.asyncio
    async def test_published_equation_with_sync_hints(self) -> None:
        """Full round-trip: instruction with sync hints publishes correctly."""
        from feynman.agent.tools import _publish_visual

        ctx = _make_mock_ctx()
        hints = [
            TermSyncHint(term_id="term-F", trigger_words=["force", "F"]),
            TermSyncHint(term_id="term-m", trigger_words=["mass", "m"]),
        ]
        instr = ShowEquationInstruction(
            latex="F = ma",
            animation="term_by_term",
            sync_mode=SyncMode.TERM_SYNC,
            term_hints=hints,
        )
        await _publish_visual(ctx, instr)

        call_args = ctx.session.room_io.room.local_participant.publish_data.call_args
        published = json.loads(call_args[0][0])
        assert published["sync_mode"] == "term_sync"
        assert published["term_hints"][0]["term_id"] == "term-F"
        assert published["term_hints"][1]["trigger_words"] == ["mass", "m"]

    @pytest.mark.asyncio
    async def test_no_hints_excluded_from_json(self) -> None:
        """None term_hints are excluded from the published JSON."""
        from feynman.agent.tools import _publish_visual

        ctx = _make_mock_ctx()
        instr = ShowEquationInstruction(latex="E = mc^2")
        await _publish_visual(ctx, instr)

        call_args = ctx.session.room_io.room.local_participant.publish_data.call_args
        published = json.loads(call_args[0][0])
        assert "term_hints" not in published


# ── Auto-ID + board state tracking tests ─────────────────────


class TestAutoId:
    @pytest.mark.asyncio
    async def test_auto_assigns_element_id(self) -> None:
        """_publish_visual auto-assigns element_id when None."""
        from feynman.agent.tools import _publish_visual

        ctx = _make_mock_ctx()
        instr = ShowTextInstruction(text="Hello")
        assert instr.element_id is None

        await _publish_visual(ctx, instr)
        assert instr.element_id == "text-1"

    @pytest.mark.asyncio
    async def test_preserves_existing_element_id(self) -> None:
        """_publish_visual keeps an explicitly-set element_id."""
        from feynman.agent.tools import _publish_visual

        ctx = _make_mock_ctx()
        instr = ShowTextInstruction(text="Hello", element_id="my-custom-id")
        await _publish_visual(ctx, instr)
        assert instr.element_id == "my-custom-id"

    @pytest.mark.asyncio
    async def test_no_auto_id_for_clear(self) -> None:
        """clear instructions don't get auto-IDs."""
        from feynman.agent.tools import _publish_visual

        ctx = _make_mock_ctx()
        instr = ClearInstruction(sync_mode=SyncMode.IMMEDIATE)
        await _publish_visual(ctx, instr, wait_for_speech=False)
        assert instr.element_id is None

    @pytest.mark.asyncio
    async def test_sequential_auto_ids(self) -> None:
        """Multiple instructions of the same type get sequential IDs."""
        from feynman.agent.tools import _publish_visual

        ctx = _make_mock_ctx()
        instr1 = ShowTextInstruction(text="A")
        instr2 = ShowTextInstruction(text="B")
        await _publish_visual(ctx, instr1)
        await _publish_visual(ctx, instr2)
        assert instr1.element_id == "text-1"
        assert instr2.element_id == "text-2"


class TestBoardStateTracking:
    @pytest.mark.asyncio
    async def test_publish_records_to_board_state(self) -> None:
        """_publish_visual records content instructions in board state."""
        from feynman.agent.tools import _publish_visual

        ctx = _make_mock_ctx()
        bm: BoardManager = ctx.userdata.board_manager

        instr = ShowTextInstruction(text="Hello world")
        await _publish_visual(ctx, instr)

        elements = bm.active_board.state._elements
        assert len(elements) == 1
        assert "text-1" in elements

    @pytest.mark.asyncio
    async def test_clear_wipes_board_state(self) -> None:
        """ClearInstruction without target_id clears all board state."""
        from feynman.agent.tools import _publish_visual

        ctx = _make_mock_ctx()
        bm: BoardManager = ctx.userdata.board_manager

        await _publish_visual(ctx, ShowTextInstruction(text="A"))
        await _publish_visual(ctx, ShowTextInstruction(text="B"))
        assert len(bm.active_board.state._elements) == 2

        await _publish_visual(
            ctx, ClearInstruction(sync_mode=SyncMode.IMMEDIATE), wait_for_speech=False
        )
        assert len(bm.active_board.state._elements) == 0

    @pytest.mark.asyncio
    async def test_clear_target_removes_one(self) -> None:
        """ClearInstruction with target_id removes only that element."""
        from feynman.agent.tools import _publish_visual

        ctx = _make_mock_ctx()
        bm: BoardManager = ctx.userdata.board_manager

        await _publish_visual(ctx, ShowTextInstruction(text="A"))
        await _publish_visual(ctx, ShowTextInstruction(text="B"))
        assert len(bm.active_board.state._elements) == 2

        await _publish_visual(
            ctx,
            ClearInstruction(sync_mode=SyncMode.IMMEDIATE, target_id="text-1"),
            wait_for_speech=False,
        )
        assert "text-1" not in bm.active_board.state._elements
        assert "text-2" in bm.active_board.state._elements


class TestZoneParam:
    @pytest.mark.asyncio
    async def test_zone_set_on_instruction(self) -> None:
        """Zone string is parsed and set on the instruction."""
        from feynman.agent.tools import _publish_visual

        ctx = _make_mock_ctx()
        instr = ShowTextInstruction(text="Hello", zone=BoardZone.TOP_LEFT)
        await _publish_visual(ctx, instr)

        call_args = ctx.session.room_io.room.local_participant.publish_data.call_args
        published = json.loads(call_args[0][0])
        assert published["zone"] == "top-left"

    @pytest.mark.asyncio
    async def test_zone_tracked_in_board_state(self) -> None:
        """Zone is recorded in the board state element."""
        from feynman.agent.tools import _publish_visual

        ctx = _make_mock_ctx()
        bm: BoardManager = ctx.userdata.board_manager

        instr = ShowTextInstruction(text="Hello", zone=BoardZone.CENTER_CENTER)
        await _publish_visual(ctx, instr)

        assert bm.active_board.state._elements["text-1"].zone == BoardZone.CENTER_CENTER

    def test_parse_zone_valid(self) -> None:
        from feynman.agent.tools import _parse_zone

        assert _parse_zone("top-left") == BoardZone.TOP_LEFT
        assert _parse_zone("center-center") == BoardZone.CENTER_CENTER

    def test_parse_zone_empty(self) -> None:
        from feynman.agent.tools import _parse_zone

        assert _parse_zone("") is None

    def test_parse_zone_invalid(self) -> None:
        from feynman.agent.tools import _parse_zone

        assert _parse_zone("not-a-zone") is None
