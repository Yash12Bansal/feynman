"""Phase 5a-3: pure helpers for the periodic drift-check state.

Lives outside ``board_verifier`` so the vision module stays focused on Haiku
calls. These helpers are stateless — the caller (worker.py's periodic loop)
owns the inputs and decides what to do with the outputs.

Two responsibilities:

* :func:`compute_drift_state_hash` — stable digest of
  ``(concept_index, sorted element_ids, per-element version)``. The worker
  loop skips a Haiku call when the digest matches the last successful check,
  which is how we hold drift-check cost in the typical $0.10/hr range.
* :func:`build_element_summary` — tuples of
  ``(element_id, original_claim, modify_count)`` ready for the drift prompt's
  element listing. Filters out elements without a retained original claim,
  sorts deterministically, and caps the list so a runaway session never
  blows up the prompt.
"""

from __future__ import annotations

import hashlib

_ELEMENT_SUMMARY_LIMIT_DEFAULT = 10


def compute_drift_state_hash(
    concept_index: int,
    element_ids: list[str],
    versions: dict[str, int],
) -> str:
    """Stable hash of ``(concept, sorted elements, per-element version)``.

    Same inputs always produce the same hash regardless of element insertion
    order. Different concepts always hash differently even when the element
    set is identical, so a concept advance reliably invalidates the dedup.
    """
    sorted_ids = sorted(element_ids)
    versioned = ",".join(f"{eid}:{versions.get(eid, 0)}" for eid in sorted_ids)
    payload = f"c{concept_index}|{versioned}".encode()
    return hashlib.sha1(payload).hexdigest()[:16]


def build_element_summary(
    visible_diagram_ids: list[str],
    original_claims: dict[str, str],
    versions: dict[str, int],
    *,
    limit: int = _ELEMENT_SUMMARY_LIMIT_DEFAULT,
) -> list[tuple[str, str, int]]:
    """Build ``(element_id, original_claim, modify_count)`` rows for the prompt.

    - Filters to elements with an ``original_claim`` recorded — without that,
      cumulative-integrity checks have nothing to compare against.
    - Sorts by version desc then element_id asc so the most-modified diagrams
      (most at risk of cumulative drift) appear first in the prompt.
    - Capped at ``limit`` so Haiku doesn't see runaway element lists.
    """
    rows = [
        (eid, original_claims[eid], versions.get(eid, 0))
        for eid in visible_diagram_ids
        if eid in original_claims
    ]
    rows.sort(key=lambda row: (-row[2], row[0]))
    return rows[:limit]
