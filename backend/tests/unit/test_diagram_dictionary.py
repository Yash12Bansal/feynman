"""Tests for DictionaryResolver — role → element_id lookup."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from feynman.agent.diagram_dictionary import DictionaryResolver


@dataclass
class _StubTC:
    """Minimal TeachingContext-shaped stub. The resolver only reads
    ``current_diagram_dictionary``."""

    current_diagram_dictionary: dict[str, Any] = field(default_factory=dict)


def _ladder_dictionary() -> dict[str, Any]:
    return {
        "side_AB": {"role": "hypotenuse", "semantic": "the ladder, 10 m"},
        "side_BC": {"role": "opposite", "semantic": "the wall"},
        "side_AC": {"role": "adjacent", "semantic": "the ground"},
        "vertex_A": {"role": "angle", "semantic": "60° at the foot"},
    }


def test_dictionary_resolver_exact_id_match() -> None:
    tc = _StubTC(current_diagram_dictionary=_ladder_dictionary())
    assert DictionaryResolver(tc).resolve("side_AB") == "side_AB"


def test_dictionary_resolver_role_lookup_case_insensitive() -> None:
    tc = _StubTC(current_diagram_dictionary=_ladder_dictionary())
    resolver = DictionaryResolver(tc)
    assert resolver.resolve("hypotenuse") == "side_AB"
    assert resolver.resolve("HYPOTENUSE") == "side_AB"
    assert resolver.resolve("Hypotenuse") == "side_AB"


def test_dictionary_resolver_role_lookup_normalizes_typos() -> None:
    tc = _StubTC(current_diagram_dictionary=_ladder_dictionary())
    resolver = DictionaryResolver(tc)
    # "hypoteneuse" is a known typo → should still find "hypotenuse".
    assert resolver.resolve("hypoteneuse") == "side_AB"
    # "opp" is the abbreviation form.
    assert resolver.resolve("opp") == "side_BC"


def test_dictionary_resolver_multi_match_returns_first() -> None:
    """If two elements share a role, the first id in iteration order wins."""
    tc = _StubTC(
        current_diagram_dictionary={
            "leg_a": {"role": "leg", "semantic": "left leg"},
            "leg_b": {"role": "leg", "semantic": "right leg"},
        }
    )
    # Iteration order in Python dicts is insertion order, so "leg_a" first.
    assert DictionaryResolver(tc).resolve("leg") == "leg_a"


def test_dictionary_resolver_no_match_falls_back_to_input() -> None:
    tc = _StubTC(current_diagram_dictionary=_ladder_dictionary())
    resolver = DictionaryResolver(tc)
    # Unknown role and not an id either → return as-is.
    assert resolver.resolve("does_not_exist") == "does_not_exist"


def test_dictionary_resolver_empty_dictionary_is_passthrough() -> None:
    tc = _StubTC(current_diagram_dictionary={})
    assert DictionaryResolver(tc).resolve("hypotenuse") == "hypotenuse"


def test_dictionary_resolver_handles_pydantic_like_meta() -> None:
    """Resolver works whether meta is a dict or has attribute access (e.g., Pydantic)."""

    class _Meta:
        def __init__(self, role: str) -> None:
            self.role = role

    tc = _StubTC(
        current_diagram_dictionary={
            "side_AB": _Meta(role="hypotenuse"),
            "vertex_A": _Meta(role="angle"),
        }
    )
    assert DictionaryResolver(tc).resolve("hypotenuse") == "side_AB"
