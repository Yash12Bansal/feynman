"""Tests for Phase 9: Metrics, Frontend Polish, Edge Cases.

Covers:
- Cache eviction on AnticipationEngine (evict_before)
- Modify timing metrics in tools.py
- Enriched SessionAudit summary (modify + doubt sections)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from feynman.agent.anticipation import AnticipationEngine
from feynman.agent.board import BoardManager
from feynman.agent.session_audit import SessionAudit

# ── Cache eviction ────────────────────────────────────────


class TestCacheEviction:
    def test_evict_removes_old_entries(self) -> None:
        """evict_before(3) removes keys with concept_index 0, 1, 2."""
        engine = AnticipationEngine()
        engine._cache = {
            (0, 0): {"title": "c0s0"},
            (1, 0): {"title": "c1s0"},
            (2, 0): {"title": "c2s0"},
            (3, 0): {"title": "c3s0"},
            (4, 0): {"title": "c4s0"},
        }
        engine._prompts = {
            (0, 0): "p0",
            (1, 0): "p1",
            (2, 0): "p2",
            (3, 0): "p3",
            (4, 0): "p4",
        }

        engine.evict_before(3)

        assert (0, 0) not in engine._cache
        assert (1, 0) not in engine._cache
        assert (2, 0) not in engine._cache
        assert (3, 0) in engine._cache
        assert (4, 0) in engine._cache
        # Prompts also cleaned up.
        assert (0, 0) not in engine._prompts
        assert (3, 0) in engine._prompts

    def test_evict_keeps_current_and_future(self) -> None:
        """Keys at concept_index >= threshold survive."""
        engine = AnticipationEngine()
        engine._cache = {(5, 0): {"title": "c5"}, (5, 1): {"title": "c5s1"}}
        engine._prompts = {(5, 0): "p5", (5, 1): "p5s1"}

        engine.evict_before(5)

        assert len(engine._cache) == 2
        assert len(engine._prompts) == 2

    def test_evict_empty_cache_noop(self) -> None:
        """No error on empty cache."""
        engine = AnticipationEngine()
        result = engine.evict_before(3)
        assert result == 0

    def test_evict_returns_count(self) -> None:
        """Return value matches evicted count."""
        engine = AnticipationEngine()
        engine._cache = {(0, 0): {}, (0, 1): {}, (1, 0): {}, (3, 0): {}}
        engine._prompts = {(0, 0): "a", (0, 1): "b", (1, 0): "c", (3, 0): "d"}

        count = engine.evict_before(2)

        assert count == 3  # (0,0), (0,1), (1,0)
        assert len(engine._cache) == 1

    def test_evict_audit_event(self) -> None:
        """Audit records cache_evicted event with count."""
        audit = SessionAudit()
        engine = AnticipationEngine(audit=audit)
        engine._cache = {(0, 0): {}, (1, 0): {}}
        engine._prompts = {(0, 0): "a", (1, 0): "b"}

        engine.evict_before(2)

        assert audit.count("anticipation", "cache_evicted") == 1
        evt = audit.events_for("anticipation")[0]
        assert evt.metadata["count"] == 2


# ── Modify timing ────────────────────────────────────────


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
    userdata.session_id = uuid4()
    # Phase 5a-2: short-circuit the diagram-verification scheduler — these
    # tests don't exercise the perception loop.
    userdata.board_verifier = None
    ctx.userdata = userdata
    return ctx


SAMPLE_SPEC: dict = {
    "title": "Free Body Diagram",
    "description": "Forces on a block",
    "elements": [
        {"id": "box", "type": "svg_rect", "x": 400, "y": 300, "width": 100, "height": 100},
    ],
}

MODIFIED_SPEC: dict = {
    "title": "Free Body Diagram",
    "description": "Forces on a block with friction",
    "elements": [
        {"id": "box", "type": "svg_rect", "x": 400, "y": 300, "width": 100, "height": 100},
        {"id": "friction", "type": "svg_arrow", "x1": 400, "y1": 350, "x2": 300, "y2": 350},
    ],
}


class TestModifyTiming:
    @pytest.mark.asyncio
    async def test_modify_records_elapsed_ms(self) -> None:
        """Audit event for modify includes elapsed_ms metadata."""
        from feynman.agent.tools import modify_design_diagram

        ctx = _make_mock_ctx()
        tc = ctx.userdata

        # Store a spec so modify can find it.
        tc.board_manager.push_board("Test Board", uuid4())
        tc.board_manager.store_design_spec("design-1", SAMPLE_SPEC)

        with patch(
            "feynman.agent.design_bridge.modify_design_diagram_spec",
            new_callable=AsyncMock,
            return_value=MODIFIED_SPEC,
        ):
            await modify_design_diagram(
                ctx, target_id="design-1", modification="add friction vector"
            )

        events = tc.audit.events_for("modify_diagram")
        assert len(events) == 1
        assert "elapsed_ms" in events[0].metadata
        assert events[0].metadata["elapsed_ms"] >= 0

    @pytest.mark.asyncio
    async def test_modify_logs_board_state(self) -> None:
        """After modify, structlog event fires with board summary."""
        from feynman.agent.tools import modify_design_diagram

        ctx = _make_mock_ctx()
        tc = ctx.userdata

        tc.board_manager.push_board("Test Board", uuid4())
        tc.board_manager.store_design_spec("design-1", SAMPLE_SPEC)

        with (
            patch(
                "feynman.agent.design_bridge.modify_design_diagram_spec",
                new_callable=AsyncMock,
                return_value=MODIFIED_SPEC,
            ),
            patch("feynman.agent.tools.logger") as mock_logger,
        ):
            await modify_design_diagram(ctx, target_id="design-1", modification="add friction")

        # Check that modify_design_diagram.complete was logged.
        complete_calls = [
            c
            for c in mock_logger.info.call_args_list
            if c.args and c.args[0] == "modify_design_diagram.complete"
        ]
        assert len(complete_calls) == 1
        assert complete_calls[0].kwargs["elapsed_ms"] >= 0


# ── Session audit summary ────────────────────────────────


class TestAuditSummaryEnriched:
    def test_summary_includes_modify_section(self) -> None:
        """Summary dict has 'modify' key with count and avg_time."""
        audit = SessionAudit()
        audit.record(
            "modify_diagram",
            "modified",
            "target=design-1",
            target_id="design-1",
            elapsed_ms=1500.0,
        )
        audit.record(
            "modify_diagram",
            "modified",
            "target=design-2",
            target_id="design-2",
            elapsed_ms=2500.0,
        )

        summary = audit.summary()

        assert summary["modify"] is not None
        assert summary["modify"]["modifications"] == 2
        assert summary["modify"]["avg_time_ms"] == 2000  # (1500+2500)/2

    def test_summary_includes_doubt_section(self) -> None:
        """Summary dict has 'doubt' key with doubt events."""
        audit = SessionAudit()
        audit.record("doubt", "background_gen_fired", "concept='gravity'")
        audit.record("doubt", "visual_ready_before_needed", "score=0.25")

        summary = audit.summary()

        assert summary["doubt"] is not None
        assert summary["doubt"]["background_gen_fired"] == 1
        assert summary["doubt"]["visual_ready_before_needed"] == 1
        assert summary["doubt"]["fallback_to_scene"] == 0

    def test_summary_text_renders_all(self) -> None:
        """summary_text() includes modify and doubt lines."""
        audit = SessionAudit()
        audit.record(
            "anticipation",
            "cache_hit",
            "concept=0",
        )
        audit.record(
            "modify_diagram",
            "modified",
            "target=design-1",
            elapsed_ms=1200.0,
        )
        audit.record("doubt", "background_gen_fired", "concept='forces'")

        text = audit.summary_text()

        assert "SESSION AUDIT" in text
        assert "MODIFY:" in text
        assert "1200ms" in text
        assert "DOUBT:" in text
        assert "bg_gen=1" in text

    def test_summary_empty_session(self) -> None:
        """No events produces graceful empty summary."""
        audit = SessionAudit()
        summary = audit.summary()

        assert summary["total_events"] == 0
        assert summary["anticipation"] is None
        assert summary["modify"] is None
        assert summary["doubt"] is None
