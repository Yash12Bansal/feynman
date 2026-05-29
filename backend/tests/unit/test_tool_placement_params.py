# TODO(DEADCODE): tests parked/dead modules (Group 1/2/3); see docs/engineering/13-redundant-code-audit.md. Safe to delete.
# """Tests for Phase 5 — tool placement params and _build_placement helper."""

# import inspect

# import pytest

# # TODO(DEADCODE): tests Group-2 interactive tools (parked); was already broken pre-session (imports removed `show_text`). See docs/engineering/13-redundant-code-audit.md Group 2. Safe to delete.
# import pytest as _deadcode_pytest
# _deadcode_pytest.skip("interactive tools tests (parked)", allow_module_level=True)
# from feynman.agent.tools import (
#     _build_placement,
#     draw_design_diagram,
#     draw_diagram,
#     draw_scene,
#     show_equation,
#     show_graph,
#     show_text,
#     step_equation,
# )
# from feynman.visuals.schemas import PlacementIntent, SizeHint


# # ── _build_placement helper ─────────────────────────────────


# class TestBuildPlacement:
#     def test_returns_none_when_no_params(self):
#         assert _build_placement("", "", "") is None

#     def test_near_only(self):
#         result = _build_placement("design-1", "", "")
#         assert isinstance(result, PlacementIntent)
#         assert result.near == "design-1"
#         assert result.relation is None
#         assert result.size_hint == SizeHint.MEDIUM

#     def test_near_with_side(self):
#         result = _build_placement("eq-2", "below", "")
#         assert result.near == "eq-2"
#         assert result.relation == "below"
#         assert result.size_hint == SizeHint.MEDIUM

#     def test_size_hint_only(self):
#         result = _build_placement("", "", "large")
#         assert isinstance(result, PlacementIntent)
#         assert result.near is None
#         assert result.relation is None
#         assert result.size_hint == SizeHint.LARGE

#     def test_invalid_size_hint_defaults_medium(self):
#         result = _build_placement("design-1", "right_of", "gigantic")
#         assert result.size_hint == SizeHint.MEDIUM

#     def test_all_params(self):
#         result = _build_placement("design-1", "right_of", "small")
#         assert result.near == "design-1"
#         assert result.relation == "right_of"
#         assert result.size_hint == SizeHint.SMALL


# # ── Tool signatures ─────────────────────────────────────────

# _VISUAL_TOOLS = [
#     show_text,
#     show_equation,
#     draw_diagram,
#     step_equation,
#     show_graph,
#     draw_design_diagram,
#     draw_scene,
# ]


# class TestToolSignatures:
#     @pytest.mark.parametrize(
#         "tool_fn",
#         _VISUAL_TOOLS,
#         ids=[fn.__name__ for fn in _VISUAL_TOOLS],
#     )
#     def test_visual_tools_have_near_param(self, tool_fn):
#         sig = inspect.signature(tool_fn)
#         assert "near" in sig.parameters, f"{tool_fn.__name__} missing 'near' param"

#     @pytest.mark.parametrize(
#         "tool_fn",
#         _VISUAL_TOOLS,
#         ids=[fn.__name__ for fn in _VISUAL_TOOLS],
#     )
#     def test_visual_tools_have_near_side_param(self, tool_fn):
#         sig = inspect.signature(tool_fn)
#         assert "near_side" in sig.parameters, f"{tool_fn.__name__} missing 'near_side' param"

#     @pytest.mark.parametrize(
#         "tool_fn",
#         _VISUAL_TOOLS,
#         ids=[fn.__name__ for fn in _VISUAL_TOOLS],
#     )
#     def test_visual_tools_have_size_hint_param(self, tool_fn):
#         sig = inspect.signature(tool_fn)
#         assert "size_hint" in sig.parameters, f"{tool_fn.__name__} missing 'size_hint' param"
