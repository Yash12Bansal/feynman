"""Tests for DrawSceneInstruction schema + draw_scene tool behavior."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from feynman.agent.board import BoardManager
from feynman.agent.board_state import BoardState, _extract_label
from feynman.visuals.schemas import (
    DrawSceneInstruction,
    SceneTemplateId,
    SceneTemplateRef,
)

# ── SceneTemplateId enum ─────────────────────────────────────


class TestSceneTemplateId:
    def test_valid_values(self) -> None:
        assert SceneTemplateId.FREE_BODY == "free_body"
        assert SceneTemplateId.DOUBLE_SLIT == "double_slit"

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            SceneTemplateId("nonexistent_template")


# ── SceneTemplateRef ──────────────────────────────────────────


class TestSceneTemplateRef:
    def test_valid_construction(self) -> None:
        ref = SceneTemplateRef(template_id=SceneTemplateId.FREE_BODY)
        assert ref.template_id == "free_body"
        assert ref.params == {}

    def test_with_params(self) -> None:
        ref = SceneTemplateRef(
            template_id=SceneTemplateId.FREE_BODY,
            params={"showWeight": True, "showFriction": False},
        )
        assert ref.params["showWeight"] is True

    def test_invalid_template_id_raises(self) -> None:
        with pytest.raises(ValueError):
            SceneTemplateRef(template_id="hallucinated_template")

    def test_serialization_roundtrip(self) -> None:
        ref = SceneTemplateRef(
            template_id=SceneTemplateId.DOUBLE_SLIT,
            params={"showWaves": True, "slitSeparation": "wide"},
        )
        data = ref.model_dump()
        restored = SceneTemplateRef(**data)
        assert restored.template_id == SceneTemplateId.DOUBLE_SLIT
        assert restored.params["slitSeparation"] == "wide"


# ── DrawSceneInstruction schema ───────────────────────────────


class TestDrawSceneInstruction:
    def test_valid_with_template(self) -> None:
        instr = DrawSceneInstruction(
            template=SceneTemplateRef(template_id=SceneTemplateId.FREE_BODY),
            description="Forces on a block",
        )
        assert instr.type == "draw_scene"
        assert instr.template is not None
        assert instr.template.template_id == "free_body"
        assert instr.progressive is True

    def test_valid_description_only(self) -> None:
        """Description-only (no template) is the fallback path."""
        instr = DrawSceneInstruction(description="A custom physics diagram")
        assert instr.template is None
        assert instr.description == "A custom physics diagram"

    def test_no_template_no_description_raises(self) -> None:
        """Must have at least template or description."""
        with pytest.raises(ValueError, match="Either template or description"):
            DrawSceneInstruction()

    def test_title_and_description(self) -> None:
        instr = DrawSceneInstruction(
            title="Free Body Diagram",
            description="Forces on a block on an inclined plane",
            template=SceneTemplateRef(
                template_id=SceneTemplateId.FREE_BODY,
                params={"showWeight": True, "showNormal": True},
            ),
        )
        assert instr.title == "Free Body Diagram"

    def test_progressive_false(self) -> None:
        instr = DrawSceneInstruction(
            description="instant",
            progressive=False,
        )
        assert instr.progressive is False

    def test_serialization_roundtrip(self) -> None:
        instr = DrawSceneInstruction(
            title="Double Slit",
            description="Young's experiment",
            template=SceneTemplateRef(
                template_id=SceneTemplateId.DOUBLE_SLIT,
                params={"showWaves": True},
            ),
        )
        data = instr.model_dump(exclude_none=True)
        assert data["type"] == "draw_scene"
        assert data["template"]["template_id"] == "double_slit"

        restored = DrawSceneInstruction.model_validate(data)
        assert restored.template is not None
        assert restored.template.params["showWaves"] is True

    def test_json_roundtrip(self) -> None:
        instr = DrawSceneInstruction(
            template=SceneTemplateRef(template_id=SceneTemplateId.FREE_BODY),
            description="FBD",
        )
        json_str = json.dumps(instr.model_dump(exclude_none=True))
        parsed = DrawSceneInstruction.model_validate_json(json_str)
        assert parsed.type == "draw_scene"
        assert parsed.template is not None


# ── Board state integration ───────────────────────────────────


class TestDrawSceneBoardState:
    def test_scene_prefix_in_type_map(self) -> None:
        bs = BoardState()
        assert bs.next_id("draw_scene") == "scene-1"
        assert bs.next_id("draw_scene") == "scene-2"

    def test_scene_tracked_as_element(self) -> None:
        bs = BoardState()
        instr = DrawSceneInstruction(
            description="Forces on a block",
            element_id="scene-1",
        )
        bs.record(instr)
        assert "scene-1" in bs._elements
        assert bs._elements["scene-1"].type == "draw_scene"

    def test_extract_label_title(self) -> None:
        instr = DrawSceneInstruction(
            title="Free Body Diagram",
            description="Forces on a block",
            template=SceneTemplateRef(template_id=SceneTemplateId.FREE_BODY),
        )
        assert _extract_label(instr) == "Free Body Diagram"

    def test_extract_label_description_fallback(self) -> None:
        instr = DrawSceneInstruction(description="A cool physics diagram")
        assert _extract_label(instr) == "A cool physics diagram"


# ── Mock helpers ──────────────────────────────────────────────


def _make_mock_ctx() -> MagicMock:
    """Create a mock RunContext matching the pattern from test_tools_sync.py."""
    ctx = MagicMock()
    ctx.wait_for_playout = AsyncMock()
    ctx.session.room_io.room.local_participant.publish_data = AsyncMock()

    userdata = MagicMock()
    userdata.board_manager = BoardManager()
    ctx.userdata = userdata

    return ctx


# ── draw_scene tool behavior ─────────────────────────────────


class TestDrawSceneTool:
    @pytest.mark.asyncio
    async def test_valid_template_publishes_instruction(self) -> None:
        from feynman.agent.tools import draw_scene

        ctx = _make_mock_ctx()

        with patch("feynman.agent.tools.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            # Call the underlying function directly (unwrap function_tool decorator)
            result = await draw_scene._func(
                ctx,
                template_id="free_body",
                title="Forces",
                description="Forces on a block",
                params_json='{"showWeight": true}',
            )

        assert "Forces" in result
        ctx.session.room_io.room.local_participant.publish_data.assert_awaited_once()

        # Verify published JSON
        call_args = ctx.session.room_io.room.local_participant.publish_data.call_args
        published = json.loads(call_args[0][0])
        assert published["type"] == "draw_scene"
        assert published["template"]["template_id"] == "free_body"
        assert published["template"]["params"]["showWeight"] is True
        assert published["title"] == "Forces"

        # Verify sleep was called for animation
        mock_sleep.assert_awaited_once_with(1.2)

    @pytest.mark.asyncio
    async def test_invalid_template_falls_back_to_description(self) -> None:
        ctx = _make_mock_ctx()

        with patch("feynman.agent.tools.asyncio.sleep", new_callable=AsyncMock):
            from feynman.agent.tools import draw_scene

            await draw_scene._func(
                ctx,
                template_id="hallucinated_template",
                description="Some diagram",
            )

        call_args = ctx.session.room_io.room.local_participant.publish_data.call_args
        published = json.loads(call_args[0][0])
        assert published["type"] == "draw_scene"
        assert published.get("template") is None
        assert published["description"] == "Some diagram"

    @pytest.mark.asyncio
    async def test_invalid_template_no_description_gets_auto_description(self) -> None:
        ctx = _make_mock_ctx()

        with patch("feynman.agent.tools.asyncio.sleep", new_callable=AsyncMock):
            from feynman.agent.tools import draw_scene

            await draw_scene._func(
                ctx,
                template_id="hallucinated_template",
            )

        call_args = ctx.session.room_io.room.local_participant.publish_data.call_args
        published = json.loads(call_args[0][0])
        assert published["type"] == "draw_scene"
        assert "hallucinated_template" in published["description"]

    @pytest.mark.asyncio
    async def test_malformed_params_json_uses_empty_params(self) -> None:
        ctx = _make_mock_ctx()

        with patch("feynman.agent.tools.asyncio.sleep", new_callable=AsyncMock):
            from feynman.agent.tools import draw_scene

            await draw_scene._func(
                ctx,
                template_id="free_body",
                description="FBD",
                params_json="not valid json{{{",
            )

        call_args = ctx.session.room_io.room.local_participant.publish_data.call_args
        published = json.loads(call_args[0][0])
        assert published["template"]["params"] == {}

    @pytest.mark.asyncio
    async def test_zone_parsing(self) -> None:
        ctx = _make_mock_ctx()

        with patch("feynman.agent.tools.asyncio.sleep", new_callable=AsyncMock):
            from feynman.agent.tools import draw_scene

            await draw_scene._func(
                ctx,
                template_id="free_body",
                description="FBD",
                zone="center-left",
            )

        call_args = ctx.session.room_io.room.local_participant.publish_data.call_args
        published = json.loads(call_args[0][0])
        assert published["zone"] == "center-left"

    @pytest.mark.asyncio
    async def test_auto_id_assigned(self) -> None:
        ctx = _make_mock_ctx()

        with patch("feynman.agent.tools.asyncio.sleep", new_callable=AsyncMock):
            from feynman.agent.tools import draw_scene

            await draw_scene._func(
                ctx,
                template_id="free_body",
                description="FBD",
            )

        call_args = ctx.session.room_io.room.local_participant.publish_data.call_args
        published = json.loads(call_args[0][0])
        assert published["element_id"] == "scene-1"

    @pytest.mark.asyncio
    async def test_double_slit_sleep_duration(self) -> None:
        ctx = _make_mock_ctx()

        with patch("feynman.agent.tools.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            from feynman.agent.tools import draw_scene

            await draw_scene._func(
                ctx,
                template_id="double_slit",
                description="Double slit experiment",
            )

        mock_sleep.assert_awaited_once_with(1.5)

    @pytest.mark.asyncio
    async def test_unknown_template_default_sleep(self) -> None:
        ctx = _make_mock_ctx()

        with patch("feynman.agent.tools.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            from feynman.agent.tools import draw_scene

            await draw_scene._func(
                ctx,
                template_id="hallucinated",
                description="Some diagram",
            )

        # Unknown template → default 1000ms = 1.0s
        mock_sleep.assert_awaited_once_with(1.0)
