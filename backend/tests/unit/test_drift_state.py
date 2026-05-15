"""Phase 5a-3 — pure helpers in ``feynman.agent.drift_state``.

These are stateless functions used by the worker's periodic drift loop. The
hash must be deterministic (so dedup works across ticks) and the summary
builder must filter/sort/cap predictably (so the drift prompt stays bounded).
"""

from __future__ import annotations

from feynman.agent.drift_state import (
    build_element_summary,
    compute_drift_state_hash,
)

# ── compute_drift_state_hash ─────────────────────────────


def test_drift_hash_deterministic() -> None:
    h1 = compute_drift_state_hash(0, ["design-1", "design-2"], {"design-1": 0, "design-2": 1})
    h2 = compute_drift_state_hash(0, ["design-1", "design-2"], {"design-1": 0, "design-2": 1})
    assert h1 == h2


def test_drift_hash_invariant_under_id_order() -> None:
    """Element-id insertion order must not change the hash."""
    h1 = compute_drift_state_hash(0, ["design-1", "design-2"], {"design-1": 0, "design-2": 1})
    h2 = compute_drift_state_hash(0, ["design-2", "design-1"], {"design-1": 0, "design-2": 1})
    assert h1 == h2


def test_drift_hash_changes_on_different_concept() -> None:
    h1 = compute_drift_state_hash(0, ["design-1"], {"design-1": 0})
    h2 = compute_drift_state_hash(1, ["design-1"], {"design-1": 0})
    assert h1 != h2


def test_drift_hash_changes_on_version_bump() -> None:
    h1 = compute_drift_state_hash(0, ["design-1"], {"design-1": 0})
    h2 = compute_drift_state_hash(0, ["design-1"], {"design-1": 1})
    assert h1 != h2


def test_drift_hash_empty_elements_is_deterministic() -> None:
    h1 = compute_drift_state_hash(5, [], {})
    h2 = compute_drift_state_hash(5, [], {})
    assert h1 == h2
    # Different concept_index still differs even with empty element list.
    assert compute_drift_state_hash(6, [], {}) != h1


# ── build_element_summary ────────────────────────────────


def test_summary_filters_elements_without_claim() -> None:
    rows = build_element_summary(
        visible_diagram_ids=["design-1", "design-2", "design-3"],
        original_claims={"design-1": "alpha", "design-3": "gamma"},
        versions={"design-1": 0, "design-2": 1, "design-3": 2},
    )
    ids = [eid for eid, _, _ in rows]
    assert ids == ["design-3", "design-1"]  # design-3 first (higher version)


def test_summary_sorts_by_version_desc_then_id_asc() -> None:
    rows = build_element_summary(
        visible_diagram_ids=["design-3", "design-1", "design-2"],
        original_claims={"design-1": "a", "design-2": "b", "design-3": "c"},
        versions={"design-1": 2, "design-2": 2, "design-3": 1},
    )
    # Both design-1 and design-2 have version 2; design-1 sorts first by id asc.
    # design-3 has version 1, lands last.
    ids = [eid for eid, _, _ in rows]
    assert ids == ["design-1", "design-2", "design-3"]


def test_summary_caps_at_limit() -> None:
    ids = [f"design-{i}" for i in range(15)]
    claims = {eid: f"claim {eid}" for eid in ids}
    versions = {eid: i for i, eid in enumerate(ids)}
    rows = build_element_summary(ids, claims, versions, limit=10)
    assert len(rows) == 10
    # The top 10 by version desc should be design-14..design-5.
    assert rows[0][0] == "design-14"
    assert rows[-1][0] == "design-5"


def test_summary_empty_inputs() -> None:
    rows = build_element_summary([], {}, {})
    assert rows == []


def test_summary_returns_tuples_with_claim_and_count() -> None:
    rows = build_element_summary(
        visible_diagram_ids=["design-1"],
        original_claims={"design-1": "free body diagram"},
        versions={"design-1": 4},
    )
    assert rows == [("design-1", "free body diagram", 4)]
