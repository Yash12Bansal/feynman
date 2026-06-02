"""Tests for the Gemini JSON-Schema downconverter (`llm/_schema_gemini.py`).

The risk this guards: Pydantic emits `$ref`/`$defs`/`anyOf`/`title` that
Gemini's function-declaration schema rejects. We assert the converter inlines
refs, collapses unions, whitelists keys, and upper-cases types — including
against the real LessonPlan / PlanJudgement schemas.
"""

from __future__ import annotations

import pytest

from lecture_pipeline_v2.curriculum.lecture_plan.lesson_judge import PlanJudgement
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_plan_models import LessonPlan
from lecture_pipeline_v2.llm._schema_gemini import to_gemini_schema

_ALLOWED = {
    "type",
    "description",
    "enum",
    "items",
    "properties",
    "required",
    "nullable",
}
_VALID_TYPES = {"OBJECT", "ARRAY", "STRING", "INTEGER", "NUMBER", "BOOLEAN"}


def _assert_clean(node: object, path: str = "root") -> None:
    """Every schema NODE must use only Gemini-allowed keys and carry a valid
    upper-case type. Property NAMES (keys under `properties`) are arbitrary and
    not validated — that's how a field literally named "title" survives."""
    assert isinstance(node, dict), f"{path}: not a dict"
    extra = set(node) - _ALLOWED
    assert not extra, f"{path}: disallowed keys {extra}"
    assert node.get("type") in _VALID_TYPES, f"{path}: bad type {node.get('type')!r}"
    if "properties" in node:
        assert node["type"] == "OBJECT", f"{path}: properties but type != OBJECT"
        for name, child in node["properties"].items():
            _assert_clean(child, f"{path}.{name}")
    if "items" in node:
        _assert_clean(node["items"], f"{path}[]")


def test_inlines_ref_and_drops_defs() -> None:
    schema = {
        "type": "object",
        "properties": {"inner": {"$ref": "#/$defs/Inner"}},
        "$defs": {
            "Inner": {
                "type": "object",
                "title": "Inner",
                "properties": {"x": {"type": "integer"}},
            }
        },
    }
    out = to_gemini_schema(schema)
    assert "$defs" not in out
    assert out["properties"]["inner"]["type"] == "OBJECT"
    assert out["properties"]["inner"]["properties"]["x"]["type"] == "INTEGER"
    assert "title" not in out["properties"]["inner"]


def test_optional_anyof_null_becomes_nullable() -> None:
    schema = {
        "type": "object",
        "properties": {
            "maybe": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        },
    }
    out = to_gemini_schema(schema)
    maybe = out["properties"]["maybe"]
    assert maybe["type"] == "STRING"
    assert maybe["nullable"] is True


def test_type_list_with_null_becomes_nullable() -> None:
    out = to_gemini_schema({"type": ["string", "null"]})
    assert out["type"] == "STRING"
    assert out["nullable"] is True


def test_enum_and_required_preserved() -> None:
    schema = {
        "type": "object",
        "properties": {"color": {"type": "string", "enum": ["red", "blue"]}},
        "required": ["color"],
    }
    out = to_gemini_schema(schema)
    assert out["properties"]["color"]["enum"] == ["red", "blue"]
    assert out["required"] == ["color"]


def test_const_becomes_single_value_enum() -> None:
    out = to_gemini_schema({"type": "object", "properties": {"k": {"const": "v"}}})
    assert out["properties"]["k"]["enum"] == ["v"]
    assert out["properties"]["k"]["type"] == "STRING"


def test_allof_single_ref_is_merged() -> None:
    schema = {
        "type": "object",
        "properties": {
            "e": {"allOf": [{"$ref": "#/$defs/E"}], "description": "an enum field"}
        },
        "$defs": {"E": {"type": "string", "enum": ["a", "b"], "title": "E"}},
    }
    out = to_gemini_schema(schema)
    e = out["properties"]["e"]
    assert e["type"] == "STRING"
    assert e["enum"] == ["a", "b"]
    assert e["description"] == "an enum field"


def test_array_items_converted() -> None:
    schema = {
        "type": "object",
        "properties": {
            "xs": {"type": "array", "items": {"$ref": "#/$defs/Item"}},
        },
        "$defs": {"Item": {"type": "object", "properties": {"n": {"type": "number"}}}},
    }
    out = to_gemini_schema(schema)
    xs = out["properties"]["xs"]
    assert xs["type"] == "ARRAY"
    assert xs["items"]["type"] == "OBJECT"
    assert xs["items"]["properties"]["n"]["type"] == "NUMBER"


def test_recursive_ref_does_not_infinite_loop() -> None:
    schema = {
        "type": "object",
        "properties": {"child": {"$ref": "#/$defs/Node"}},
        "$defs": {
            "Node": {
                "type": "object",
                "properties": {"child": {"$ref": "#/$defs/Node"}},
            }
        },
    }
    out = to_gemini_schema(schema)  # must terminate
    assert out["type"] == "OBJECT"


@pytest.mark.parametrize("model", [LessonPlan, PlanJudgement])
def test_real_pydantic_schemas_are_gemini_clean(model: type) -> None:
    out = to_gemini_schema(model.model_json_schema())
    _assert_clean(out)
    assert out["type"] == "OBJECT"
    assert out["properties"], "expected a non-empty properties map"
