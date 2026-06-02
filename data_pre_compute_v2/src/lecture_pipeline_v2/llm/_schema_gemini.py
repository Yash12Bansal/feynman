"""Convert a Pydantic JSON Schema into Gemini's function-declaration subset.

Gemini function calling accepts only an OpenAPI-3.0-ish subset:
- `$ref` / `$defs` are NOT supported  → we inline (dereference) them.
- `anyOf`/`oneOf`/`allOf` are unsupported (older API) → we collapse them
  (Optional `T | null` → `T` + `nullable: true`; unions → first concrete branch).
- Unknown keywords (`title`, `default`, `additionalProperties`, constraints…)
  are rejected → we WHITELIST the supported keys and drop the rest.
- `type` must be the upper-case OpenAPI enum (STRING, OBJECT, …).

Pydantic re-validates the real constraints on our side after the model
returns, so dropping constraint keywords here is lossless for correctness.

Pure functions, no SDK import — unit-testable without `google-genai` installed.
"""

from __future__ import annotations

from typing import Any

_MAX_DEPTH = 50

_TYPE_MAP = {
    "object": "OBJECT",
    "array": "ARRAY",
    "string": "STRING",
    "integer": "INTEGER",
    "number": "NUMBER",
    "boolean": "BOOLEAN",
}

# Keys Gemini's Schema accepts (after we normalize them).
_ALLOWED_KEYS = {"type", "description", "enum", "items", "properties", "required"}


def to_gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Dereference + downconvert a Pydantic JSON Schema for Gemini.

    Guarantees the result contains no `$ref`/`$defs`/`anyOf`/`allOf` and that
    every node carries an upper-case `type`.
    """
    defs = schema.get("$defs") or schema.get("definitions") or {}
    return _convert(schema, defs, 0, frozenset())


def _convert(
    node: Any, defs: dict[str, Any], depth: int, seen: frozenset[str]
) -> dict[str, Any]:
    if not isinstance(node, dict):
        return {"type": "STRING"}
    if depth > _MAX_DEPTH:
        return {"type": "STRING", "description": "max-depth truncated"}

    # 1) $ref — inline the referenced definition (with cycle guard).
    if "$ref" in node:
        return _resolve_ref(node, defs, depth, seen)

    # 2) allOf — Pydantic uses single-element allOf to attach a description to
    #    a $ref. Merge shallowly.
    if "allOf" in node:
        return _merge_all_of(node, defs, depth, seen)

    # 3) anyOf/oneOf — collapse (handles Optional and best-effort unions).
    for union_key in ("anyOf", "oneOf"):
        if union_key in node:
            return _collapse_union(node, node[union_key], defs, depth, seen)

    out: dict[str, Any] = {}

    # 4) const → single-value enum.
    if "const" in node:
        out["type"] = _TYPE_MAP.get(_json_type_of(node["const"]), "STRING")
        out["enum"] = [node["const"]]
        if isinstance(node.get("description"), str):
            out["description"] = node["description"]
        return out

    nullable = False
    for key, value in node.items():
        if key not in _ALLOWED_KEYS:
            continue
        if key == "type":
            mapped, was_nullable = _map_type(value)
            out["type"] = mapped
            nullable = nullable or was_nullable
        elif key == "properties" and isinstance(value, dict):
            out["properties"] = {
                pk: _convert(pv, defs, depth + 1, seen) for pk, pv in value.items()
            }
        elif key == "items":
            out["items"] = _convert(value, defs, depth + 1, seen)
        else:  # enum, required, description
            out[key] = value

    if "type" not in out:
        out["type"] = "OBJECT" if "properties" in out else "STRING"
    if nullable:
        out["nullable"] = True
    return out


def _resolve_ref(
    node: dict[str, Any], defs: dict[str, Any], depth: int, seen: frozenset[str]
) -> dict[str, Any]:
    name = node["$ref"].split("/")[-1]
    if name in seen:
        return {"type": "OBJECT", "description": f"recursive ref to {name}"}
    target = defs.get(name)
    if not isinstance(target, dict):
        return {"type": "STRING"}
    converted = _convert(target, defs, depth + 1, seen | {name})
    if isinstance(node.get("description"), str) and "description" not in converted:
        converted["description"] = node["description"]
    return converted


def _merge_all_of(
    node: dict[str, Any], defs: dict[str, Any], depth: int, seen: frozenset[str]
) -> dict[str, Any]:
    subs = [s for s in node["allOf"] if isinstance(s, dict)]
    if len(subs) == 1:
        converted = _convert(subs[0], defs, depth + 1, seen)
        if isinstance(node.get("description"), str) and "description" not in converted:
            converted["description"] = node["description"]
        return converted
    merged: dict[str, Any] = {"type": "OBJECT", "properties": {}}
    required: list[str] = []
    for sub in subs:
        converted = _convert(sub, defs, depth + 1, seen)
        merged["properties"].update(converted.get("properties", {}))
        required.extend(converted.get("required", []))
    if required:
        merged["required"] = required
    if isinstance(node.get("description"), str):
        merged["description"] = node["description"]
    return merged


def _collapse_union(
    node: dict[str, Any],
    options: Any,
    defs: dict[str, Any],
    depth: int,
    seen: frozenset[str],
) -> dict[str, Any]:
    opts = [o for o in options if isinstance(o, dict)]
    nullable = any(o.get("type") == "null" for o in opts)
    concrete = [o for o in opts if o.get("type") != "null"]
    if not concrete:
        return {"type": "STRING", "nullable": True}
    converted = _convert(concrete[0], defs, depth + 1, seen)
    if nullable:
        converted["nullable"] = True
    if isinstance(node.get("description"), str) and "description" not in converted:
        converted["description"] = node["description"]
    return converted


def _map_type(value: Any) -> tuple[str, bool]:
    """Map a JSON-schema `type` (string or list) to (gemini_type, nullable)."""
    if isinstance(value, list):
        non_null = [t for t in value if t != "null"]
        mapped = _TYPE_MAP.get(non_null[0], "STRING") if non_null else "STRING"
        return mapped, "null" in value
    return _TYPE_MAP.get(value, "STRING"), False


def _json_type_of(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return "string"
