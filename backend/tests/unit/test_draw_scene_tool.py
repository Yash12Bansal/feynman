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
    SemanticSceneElement,
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
        """Must have at least template, description, or elements."""
        with pytest.raises(ValueError, match="Either template, description, or elements"):
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
    userdata.current_concept = None
    userdata.lesson_plan = None
    # Phase 5a-2: short-circuit the diagram-verification scheduler — these
    # tests don't exercise the perception loop.
    userdata.board_verifier = None
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


# ── SemanticSceneElement schema ──────────────────────────────


class TestSemanticSceneElement:
    def test_all_fields(self) -> None:
        elem = SemanticSceneElement(
            id="f1",
            kind="force_arrow",
            label="Weight",
            from_ref="block",
            to="ground",
            direction="down",
            angle=270.0,
            magnitude=9.8,
            color="#ff0000",
            extras={"dashArray": "5,5"},
        )
        assert elem.id == "f1"
        assert elem.kind == "force_arrow"
        assert elem.from_ref == "block"
        assert elem.extras == {"dashArray": "5,5"}

    def test_minimal(self) -> None:
        elem = SemanticSceneElement(id="b1", kind="box")
        assert elem.label is None
        assert elem.from_ref is None
        assert elem.to is None

    def test_from_alias_round_trip(self) -> None:
        """Wire format uses 'from', Python uses 'from_ref'."""
        # Parse from wire format (using alias)
        elem = SemanticSceneElement.model_validate(
            {"id": "f1", "kind": "force_arrow", "from": "block"}
        )
        assert elem.from_ref == "block"

        # Serialize back to wire format (using alias)
        data = elem.model_dump(exclude_none=True, by_alias=True)
        assert "from" in data
        assert "from_ref" not in data
        assert data["from"] == "block"

    def test_populate_by_name(self) -> None:
        """Can also construct using the Python field name."""
        elem = SemanticSceneElement(id="f1", kind="force_arrow", from_ref="block")
        assert elem.from_ref == "block"


# ── DrawSceneInstruction with semantic spec ──────────────────


class TestDrawSceneInstructionSemantic:
    def test_valid_with_scene_type_and_elements(self) -> None:
        instr = DrawSceneInstruction(
            scene_type="free_body",
            elements=[SemanticSceneElement(id="b", kind="box")],
        )
        assert instr.scene_type == "free_body"
        assert len(instr.elements) == 1

    def test_elements_without_scene_type_raises(self) -> None:
        with pytest.raises(ValueError, match="scene_type is required"):
            DrawSceneInstruction(
                elements=[SemanticSceneElement(id="b", kind="box")],
            )

    def test_no_content_raises(self) -> None:
        with pytest.raises(ValueError, match="Either template, description, or elements"):
            DrawSceneInstruction()

    def test_backward_compat_template_only(self) -> None:
        """Existing template-only path still works."""
        instr = DrawSceneInstruction(
            template=SceneTemplateRef(template_id=SceneTemplateId.FREE_BODY),
            description="Forces on a block",
        )
        assert instr.template is not None
        assert instr.scene_type is None
        assert instr.elements == []

    def test_backward_compat_description_only(self) -> None:
        instr = DrawSceneInstruction(description="A physics diagram")
        assert instr.template is None
        assert instr.scene_type is None

    def test_serialization_with_alias(self) -> None:
        """Elements with from_ref serialize as 'from' on the wire."""
        instr = DrawSceneInstruction(
            scene_type="free_body",
            elements=[
                SemanticSceneElement(id="b", kind="box"),
                SemanticSceneElement(id="f1", kind="force_arrow", from_ref="b", direction="down"),
            ],
        )
        data = instr.model_dump(exclude_none=True, by_alias=True)
        assert data["scene_type"] == "free_body"
        assert len(data["elements"]) == 2
        arrow = data["elements"][1]
        assert arrow["from"] == "b"
        assert "from_ref" not in arrow


# ── draw_scene tool: semantic path ───────────────────────────


class TestDrawSceneToolSemantic:
    @pytest.mark.asyncio
    async def test_semantic_path_publishes_instruction(self) -> None:
        from feynman.agent.tools import draw_scene

        ctx = _make_mock_ctx()
        elements = [{"id": "b", "kind": "box"}, {"id": "f1", "kind": "force_arrow", "from": "b"}]

        with patch("feynman.agent.tools.asyncio.sleep", new_callable=AsyncMock):
            result = await draw_scene._func(
                ctx,
                scene_type="free_body",
                elements_json=json.dumps(elements),
                title="Forces",
                description="FBD",
            )

        assert "Forces" in result
        call_args = ctx.session.room_io.room.local_participant.publish_data.call_args
        published = json.loads(call_args[0][0])
        assert published["type"] == "draw_scene"
        assert published["scene_type"] == "free_body"
        assert len(published["elements"]) == 2
        # Verify alias serialization: "from" not "from_ref"
        assert published["elements"][1]["from"] == "b"
        assert "from_ref" not in published["elements"][1]

    @pytest.mark.asyncio
    async def test_invalid_elements_json_falls_back(self) -> None:
        from feynman.agent.tools import draw_scene

        ctx = _make_mock_ctx()

        with patch("feynman.agent.tools.asyncio.sleep", new_callable=AsyncMock):
            await draw_scene._func(
                ctx,
                scene_type="free_body",
                elements_json="not valid json{{{",
                description="FBD fallback",
            )

        # Falls through to description-only (elements list is empty after bad parse)
        call_args = ctx.session.room_io.room.local_participant.publish_data.call_args
        published = json.loads(call_args[0][0])
        assert published["description"] == "FBD fallback"
        # No elements in output (fell through to template/description path)
        assert (
            published.get("scene_type") is None
            or "elements" not in published
            or published["elements"] == []
        )

    @pytest.mark.asyncio
    async def test_semantic_takes_priority_over_template(self) -> None:
        from feynman.agent.tools import draw_scene

        ctx = _make_mock_ctx()
        elements = [{"id": "b", "kind": "box"}]

        with patch("feynman.agent.tools.asyncio.sleep", new_callable=AsyncMock):
            await draw_scene._func(
                ctx,
                template_id="free_body",
                scene_type="free_body",
                elements_json=json.dumps(elements),
                description="FBD",
            )

        call_args = ctx.session.room_io.room.local_participant.publish_data.call_args
        published = json.loads(call_args[0][0])
        # Semantic path won — scene_type + elements present, no template
        assert published["scene_type"] == "free_body"
        assert len(published["elements"]) == 1
        assert published.get("template") is None

    @pytest.mark.asyncio
    async def test_neither_template_nor_semantic_uses_description(self) -> None:
        from feynman.agent.tools import draw_scene

        ctx = _make_mock_ctx()

        with patch("feynman.agent.tools.asyncio.sleep", new_callable=AsyncMock):
            await draw_scene._func(
                ctx,
                description="Just a description",
            )

        call_args = ctx.session.room_io.room.local_participant.publish_data.call_args
        published = json.loads(call_args[0][0])
        assert published["description"] == "Just a description"
        assert published.get("template") is None
        assert published.get("scene_type") is None

    @pytest.mark.asyncio
    async def test_semantic_animation_duration(self) -> None:
        """3 elements → base 800ms + 3*150ms = 1250ms → 1.25s sleep."""
        from feynman.agent.tools import draw_scene

        ctx = _make_mock_ctx()
        elements = [
            {"id": "b", "kind": "box"},
            {"id": "f1", "kind": "force_arrow"},
            {"id": "f2", "kind": "force_arrow"},
        ]

        with patch("feynman.agent.tools.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await draw_scene._func(
                ctx,
                scene_type="free_body",
                elements_json=json.dumps(elements),
            )

        mock_sleep.assert_awaited_once_with(1.25)

    @pytest.mark.asyncio
    async def test_no_args_gets_fallback_description(self) -> None:
        """Calling with zero args produces a description-only fallback."""
        from feynman.agent.tools import draw_scene

        ctx = _make_mock_ctx()

        with patch("feynman.agent.tools.asyncio.sleep", new_callable=AsyncMock):
            await draw_scene._func(ctx)

        call_args = ctx.session.room_io.room.local_participant.publish_data.call_args
        published = json.loads(call_args[0][0])
        assert published["description"] == "Scientific diagram"
