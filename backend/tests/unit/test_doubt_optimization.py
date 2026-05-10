"""Tests for Phase 8: Doubt Branch Optimization.

Covers:
- Doubt cache on AnticipationEngine (warm_doubt, match, clear)
- Background visual generation in start_doubt_branch
- Doubt cache cleanup in resolve_doubt
- draw_design_diagram fallback behavior
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from feynman.agent.anticipation import AnticipationEngine
from feynman.agent.board import BoardManager
from feynman.agent.session_audit import SessionAudit

# ── Sample specs ────────────────────────────────────────────

DOUBT_SPEC: dict = {
    "title": "Number Line Multiplication",
    "description": "Explaining negative x negative",
    "elements": [
        {"id": "line", "type": "svg_line", "x1": 50, "y1": 300, "x2": 850, "y2": 300},
        {"id": "label-neg", "type": "svg_text", "text": "-3", "x": 200, "y": 280},
    ],
}


# ── Doubt cache storage ────────────────────────────────────


class TestDoubtCacheStorage:
    @pytest.mark.asyncio
    async def test_warm_stores_spec(self) -> None:
        """warm_doubt generates and stores the spec."""
        engine = AnticipationEngine()
        with patch(
            "feynman.agent.design_bridge.generate_design_diagram",
            new_callable=AsyncMock,
            return_value=DOUBT_SPEC,
        ):
            await engine.warm_doubt("why negative times negative is positive")

        assert engine._doubt_spec is DOUBT_SPEC
        assert "negative" in engine._doubt_prompt

    @pytest.mark.asyncio
    async def test_warm_includes_context(self) -> None:
        """Prompt includes board_summary and parent_concept when provided."""
        engine = AnticipationEngine()
        with patch(
            "feynman.agent.design_bridge.generate_design_diagram",
            new_callable=AsyncMock,
            return_value=DOUBT_SPEC,
        ) as mock_gen:
            await engine.warm_doubt(
                "why gravity pulls down",
                board_summary="eq-1: F=ma, design-1: Free body diagram",
                parent_concept="Newton's Laws",
            )

            # The prompt passed to generate_design_diagram should contain context.
            call_prompt = mock_gen.call_args[0][0]
            assert "gravity pulls down" in call_prompt
            assert "Newton's Laws" in call_prompt
            assert "Free body diagram" in call_prompt

    @pytest.mark.asyncio
    async def test_warm_failure_silent(self) -> None:
        """Generation failure does not raise — _doubt_spec stays None."""
        engine = AnticipationEngine()
        with patch(
            "feynman.agent.design_bridge.generate_design_diagram",
            new_callable=AsyncMock,
            side_effect=ValueError("API error"),
        ):
            await engine.warm_doubt("some concept")  # Should not raise

        assert engine._doubt_spec is None
        assert engine._doubt_prompt != ""  # Prompt was still set


# ── Doubt cache matching ───────────────────────────────────


class TestDoubtCacheMatching:
    def test_match_returns_doubt_spec(self) -> None:
        """match() returns doubt spec when prompt has reasonable overlap."""
        engine = AnticipationEngine()
        engine._doubt_spec = DOUBT_SPEC
        engine._doubt_prompt = (
            "A student has a doubt about: negative times negative positive"
            "\nDraw a clear, focused diagram that helps explain this concept."
        )

        # Agent's draw prompt overlaps enough with doubt prompt tokens.
        result = engine.match("Draw diagram explaining negative times negative", concept_index=0)
        assert result is DOUBT_SPEC

    def test_match_doubt_one_shot(self) -> None:
        """After returning doubt spec once, second match returns None."""
        engine = AnticipationEngine()
        engine._doubt_spec = DOUBT_SPEC
        engine._doubt_prompt = "A student has a doubt about: negative multiplication"

        first = engine.match("negative multiplication diagram", concept_index=0)
        assert first is DOUBT_SPEC

        second = engine.match("negative multiplication diagram", concept_index=0)
        assert second is None

    def test_match_no_doubt_normal_search(self) -> None:
        """Without _doubt_spec set, normal cache search runs."""
        engine = AnticipationEngine()
        # No doubt spec set — should search regular cache (empty here → None).
        result = engine.match("draw a free body diagram", concept_index=0)
        assert result is None

    def test_match_doubt_low_similarity_falls_through(self) -> None:
        """Completely unrelated prompt doesn't match doubt spec."""
        engine = AnticipationEngine()
        engine._doubt_spec = DOUBT_SPEC
        engine._doubt_prompt = (
            "A student has a doubt about: why negative times negative is positive"
        )

        # Totally unrelated prompt — should NOT match.
        result = engine.match("photosynthesis chloroplast cell diagram", concept_index=0)
        assert result is None
        # Doubt spec should still be available (not consumed).
        assert engine._doubt_spec is DOUBT_SPEC


# ── Clear ──────────────────────────────────────────────────


class TestClearDoubtCache:
    def test_clear_removes_spec(self) -> None:
        engine = AnticipationEngine()
        engine._doubt_spec = DOUBT_SPEC
        engine._doubt_prompt = "some prompt"

        engine.clear_doubt_cache()

        assert engine._doubt_spec is None
        assert engine._doubt_prompt == ""


# ── Audit events ───────────────────────────────────────────


class TestDoubtAuditEvents:
    @pytest.mark.asyncio
    async def test_warm_fires_audit_event(self) -> None:
        """warm_doubt records 'doubt/background_gen_fired' audit event."""
        audit = SessionAudit()
        engine = AnticipationEngine(audit=audit)
        with patch(
            "feynman.agent.design_bridge.generate_design_diagram",
            new_callable=AsyncMock,
            return_value=DOUBT_SPEC,
        ):
            await engine.warm_doubt("gravity question")

        assert audit.count("doubt", "background_gen_fired") == 1

    def test_match_doubt_fires_audit_event(self) -> None:
        """match() records 'doubt/visual_ready_before_needed' on doubt cache hit."""
        audit = SessionAudit()
        engine = AnticipationEngine(audit=audit)
        engine._doubt_spec = DOUBT_SPEC
        engine._doubt_prompt = "A student has a doubt about: gravity and forces"

        engine.match("draw diagram about gravity forces", concept_index=0)

        assert audit.count("doubt", "visual_ready_before_needed") == 1


# ── Integration with tools ─────────────────────────────────


def _make_mock_ctx(board_manager: BoardManager | None = None) -> MagicMock:
    """Create a mock RunContext with TeachingContext userdata."""
    ctx = MagicMock()
    ctx.wait_for_playout = AsyncMock()
    ctx.session.room_io.room.local_participant.publish_data = AsyncMock()
    ctx.session.current_agent.update_instructions = AsyncMock()

    userdata = MagicMock()
    userdata.board_manager = board_manager or BoardManager()
    userdata.audit = SessionAudit()
    userdata.current_concept_index = 0
    userdata.current_concept = None
    userdata.lesson_plan = None
    userdata.anticipation = AnticipationEngine(audit=userdata.audit)
    userdata.state_machine = MagicMock()
    userdata.state_machine.depth = 1
    userdata.state_machine.current = MagicMock(id=uuid4())
    userdata.session_id = uuid4()
    userdata.active_highlights = []
    userdata.active_annotations = []
    userdata.last_beat_index = 0
    userdata.current_diagram_dictionary = {}
    # Phase 2A: orchestrator hooks must be awaitable / callable. Default to
    # no-op mocks so tests that don't care about doubt_orchestrator behaviour
    # don't have to stub it themselves.
    userdata.doubt_orchestrator = MagicMock()
    userdata.doubt_orchestrator.on_push = AsyncMock()
    userdata.doubt_orchestrator.on_pop = AsyncMock()
    userdata.doubt_orchestrator.on_tool_invoked = MagicMock()
    userdata.doubt_orchestrator.is_resolution_allowed = MagicMock(return_value=(True, ""))
    userdata.doubt_orchestrator.get_state = MagicMock(return_value=None)
    ctx.userdata = userdata
    return ctx


class TestStartDoubtBranchWarming:
    @pytest.mark.asyncio
    async def test_fires_background_warmup(self) -> None:
        """start_doubt_branch fires warm_doubt as a background task."""
        from feynman.agent.tools import start_doubt_branch

        ctx = _make_mock_ctx()
        tc = ctx.userdata
        # Make push_branch return a branch-like object.
        tc.state_machine.push_branch = AsyncMock(return_value=MagicMock(id=uuid4()))

        with patch.object(tc.anticipation, "warm_doubt", new_callable=AsyncMock) as mock_warm:
            await start_doubt_branch(ctx, related_concept="why F=ma")
            # warm_doubt should have been called (via create_task).
            # Give the task a chance to fire.
            import asyncio

            await asyncio.sleep(0)
            mock_warm.assert_awaited_once()
            assert "F=ma" in mock_warm.call_args[0][0]

    @pytest.mark.asyncio
    async def test_resolve_clears_doubt_cache(self) -> None:
        """resolve_doubt calls clear_doubt_cache."""
        from feynman.agent.tools import resolve_doubt

        ctx = _make_mock_ctx()
        tc = ctx.userdata
        tc.state_machine.depth = 2  # In a doubt branch.
        tc.state_machine.pop_branch = AsyncMock(return_value=MagicMock(concept="gravity"))
        tc.anticipation._doubt_spec = DOUBT_SPEC
        tc.anticipation._doubt_prompt = "some prompt"

        # Push a board so pop_board() has something to pop.
        tc.board_manager.push_board("Doubt: gravity", uuid4())

        await resolve_doubt(ctx)

        assert tc.anticipation._doubt_spec is None
        assert tc.anticipation._doubt_prompt == ""


# ── Fallback ───────────────────────────────────────────────


class TestDrawDesignDiagramFallback:
    @pytest.mark.asyncio
    async def test_fallback_suggests_draw_scene(self) -> None:
        """On generation failure, error message references draw_scene."""
        from feynman.agent.tools import draw_design_diagram

        ctx = _make_mock_ctx()
        tc = ctx.userdata
        tc.anticipation.match = MagicMock(return_value=None)

        with patch(
            "feynman.agent.design_bridge.generate_design_diagram",
            new_callable=AsyncMock,
            side_effect=RuntimeError("API down"),
        ):
            result = await draw_design_diagram(ctx, prompt="draw a lens diagram")

        assert "draw_scene" in result
        assert "Failed" in result

    @pytest.mark.asyncio
    async def test_fallback_audit_event(self) -> None:
        """On generation failure, audit records doubt/fallback_to_scene."""
        from feynman.agent.tools import draw_design_diagram

        ctx = _make_mock_ctx()
        tc = ctx.userdata
        tc.anticipation.match = MagicMock(return_value=None)

        with patch(
            "feynman.agent.design_bridge.generate_design_diagram",
            new_callable=AsyncMock,
            side_effect=RuntimeError("API down"),
        ):
            await draw_design_diagram(ctx, prompt="draw a lens diagram")

        assert tc.audit.count("doubt", "fallback_to_scene") == 1
