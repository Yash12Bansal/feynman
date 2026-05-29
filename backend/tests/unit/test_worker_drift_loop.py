# TODO(DEADCODE): tests parked/dead modules (Group 1/2/3); see docs/engineering/13-redundant-code-audit.md. Safe to delete.
# """Phase 5a-3 — worker.py periodic drift-check helpers.

# Tests the pre-flight (``_should_run_drift_check``) and the synchronous body
# of the drift tick (``_run_drift_check``). Excludes the actual asyncio loop —
# that's a thin sleep/try/except wrapper not worth unit testing.
# """

# from __future__ import annotations

# from typing import Any
# from unittest.mock import AsyncMock, MagicMock
# from uuid import uuid4

# import pytest

# from feynman.agent.board_verifier import (
#     DriftCheckResult,
#     PerceptionFeedback,
# )
# from feynman.agent.session_audit import SessionAudit
# from feynman.agent.state_machine import TeachingStateMachine
# from feynman.agent.teaching_context import TeachingContext
# # TODO(DEADCODE): module tests interactive live-teaching worker internals (parked). See docs/engineering/13-redundant-code-audit.md Group 2. Safe to delete.
# import pytest as _deadcode_pytest
# _deadcode_pytest.skip(
#     "interactive worker tests (parked) — see docs/engineering/13-redundant-code-audit.md Group 2",
#     allow_module_level=True,
# )
# from feynman.livekit.worker import (
#     DRIFT_FEEDBACK_BUDGET_PER_CONCEPT,
#     _run_drift_check,
#     _should_run_drift_check,
# )


# def _make_tc(*, depth: int = 1, design_ids: list[str] | None = None) -> TeachingContext:
#     """Construct a TeachingContext with the bits the drift helpers read.

#     ``state_machine`` is a real instance (cheap), but we override ``depth`` via
#     a MagicMock substitution for the cases that need a doubt branch. Board
#     manager + current_concept are MagicMocks because their full setup adds
#     noise without changing behaviour.
#     """
#     session_id = uuid4()
#     real_sm = TeachingStateMachine(session_id=session_id)
#     tc = TeachingContext(session_id=session_id, state_machine=real_sm)
#     tc.audit = SessionAudit()

#     # state_machine depth override
#     if depth != 1:
#         tc.state_machine = MagicMock()
#         tc.state_machine.depth = depth
#     # board manager with controllable _design_specs
#     tc.board_manager = MagicMock()
#     tc.board_manager.active_board.state._design_specs = {eid: {} for eid in (design_ids or [])}
#     # default board_verifier (tests override individually)
#     tc.board_verifier = MagicMock()

#     # current_concept is a @property that reads lesson_plan.concept_at(idx) —
#     # stub the plan so the property resolves to a concept with title +
#     # description the drift helpers consume.
#     concept = MagicMock()
#     concept.title = "Free body diagrams"
#     concept.description = "Draw forces on objects"
#     lesson_plan = MagicMock()
#     lesson_plan.total_concepts = 5
#     lesson_plan.concept_at = MagicMock(return_value=concept)
#     tc.lesson_plan = lesson_plan
#     return tc


# # ── _should_run_drift_check ──────────────────────────────


# def test_should_run_returns_false_when_no_verifier() -> None:
#     tc = _make_tc(design_ids=["design-1"])
#     tc.board_verifier = None
#     assert _should_run_drift_check(tc) is False


# def test_should_run_skips_in_doubt_branch() -> None:
#     tc = _make_tc(depth=2, design_ids=["design-1"])
#     assert _should_run_drift_check(tc) is False
#     skipped = tc.audit.events_for("drift_check")
#     assert any(e.event == "skipped_doubt_branch" for e in skipped)


# def test_should_run_skips_when_no_current_concept() -> None:
#     tc = _make_tc(design_ids=["design-1"])
#     tc.lesson_plan = None  # no plan → no current_concept
#     assert _should_run_drift_check(tc) is False
#     skipped = tc.audit.events_for("drift_check")
#     assert any(e.event == "skipped_no_concept" for e in skipped)


# def test_should_run_skips_with_no_diagrams() -> None:
#     tc = _make_tc(design_ids=[])
#     assert _should_run_drift_check(tc) is False
#     skipped = tc.audit.events_for("drift_check")
#     assert any(e.event == "skipped_no_diagrams" for e in skipped)


# def test_should_run_skips_when_hash_unchanged() -> None:
#     tc = _make_tc(design_ids=["design-1"])
#     tc.diagram_version = {"design-1": 0}
#     # First call computes and skips comparison — we set the hash explicitly to
#     # exercise the dedup branch.
#     from feynman.agent.drift_state import compute_drift_state_hash

#     expected = compute_drift_state_hash(0, ["design-1"], {"design-1": 0})
#     tc.last_drift_check_hash = expected
#     assert _should_run_drift_check(tc) is False
#     skipped = tc.audit.events_for("drift_check")
#     assert any(e.event == "skipped_unchanged" for e in skipped)


# def test_should_run_skips_when_concept_budget_full() -> None:
#     tc = _make_tc(design_ids=["design-1"])
#     tc.drift_feedback_budget_used[0] = DRIFT_FEEDBACK_BUDGET_PER_CONCEPT
#     assert _should_run_drift_check(tc) is False
#     skipped = tc.audit.events_for("drift_check")
#     assert any(e.event == "skipped_budget" for e in skipped)


# def test_should_run_returns_true_when_all_conditions_met() -> None:
#     tc = _make_tc(design_ids=["design-1"])
#     tc.diagram_version = {"design-1": 0}
#     tc.last_drift_check_hash = None
#     assert _should_run_drift_check(tc) is True


# # ── _run_drift_check ─────────────────────────────────────


# def _consistent_result(state_hash: str) -> DriftCheckResult:
#     return DriftCheckResult(
#         is_consistent=True,
#         drift_kind=None,
#         affected_element_id=None,
#         issue="",
#         suggested_action="",
#         concept_index=0,
#         concept_title="Free body diagrams",
#         state_hash=state_hash,
#     )


# @pytest.mark.asyncio
# async def test_run_drift_check_commits_hash_on_success() -> None:
#     tc = _make_tc(design_ids=["design-1"])
#     tc.diagram_version = {"design-1": 0}
#     tc.original_diagram_claims = {"design-1": "claim"}

#     from feynman.agent.drift_state import compute_drift_state_hash

#     expected_hash = compute_drift_state_hash(0, ["design-1"], {"design-1": 0})

#     request_drift_check = AsyncMock(return_value=_consistent_result(expected_hash))
#     tc.board_verifier.request_drift_check = request_drift_check

#     await _run_drift_check(tc)
#     request_drift_check.assert_awaited_once()
#     assert tc.last_drift_check_hash == expected_hash


# @pytest.mark.asyncio
# async def test_run_drift_check_leaves_hash_untouched_on_exception() -> None:
#     tc = _make_tc(design_ids=["design-1"])
#     tc.last_drift_check_hash = "previous_hash"
#     tc.original_diagram_claims = {"design-1": "claim"}

#     tc.board_verifier.request_drift_check = AsyncMock(return_value=None)

#     await _run_drift_check(tc)
#     # No new commit on None result.
#     assert tc.last_drift_check_hash == "previous_hash"


# @pytest.mark.asyncio
# async def test_run_drift_check_callback_enqueues_feedback_and_increments_budget() -> None:
#     tc = _make_tc(design_ids=["design-1"])
#     tc.original_diagram_claims = {"design-1": "claim"}

#     captured_feedback: list[PerceptionFeedback] = []

#     async def _fake_request_drift_check(**kwargs: Any) -> DriftCheckResult:
#         # Caller passes us the on_feedback closure — exercise it.
#         fb = PerceptionFeedback(
#             tool_name="periodic_drift_check",
#             original_claim="Free body diagrams",
#             score=0,
#             issue="x",
#             drift_kind="concept_fit",
#             suggested_action="y",
#             target_diagram_id="design-1",
#         )
#         kwargs["on_feedback"](fb, _consistent_result(kwargs["state_hash"]))
#         captured_feedback.append(fb)
#         return _consistent_result(kwargs["state_hash"])

#     tc.board_verifier.request_drift_check = _fake_request_drift_check

#     await _run_drift_check(tc)
#     # Queue should now hold the feedback the closure routed.
#     assert len(tc.perception_feedback_queue) == 1
#     assert tc.perception_feedback_queue[0] is captured_feedback[0]
#     assert tc.drift_feedback_budget_used.get(0) == 1


# @pytest.mark.asyncio
# async def test_run_drift_check_callback_drops_when_concept_advanced() -> None:
#     tc = _make_tc(design_ids=["design-1"])
#     tc.original_diagram_claims = {"design-1": "claim"}

#     async def _fake_request_drift_check(**kwargs: Any) -> DriftCheckResult:
#         # Advance the concept BEFORE the callback fires — simulates a slow
#         # vision call where the agent moved on while we were still mid-flight.
#         tc.current_concept_index = 1
#         fb = PerceptionFeedback(
#             tool_name="periodic_drift_check",
#             original_claim="x",
#             score=0,
#             issue="x",
#             drift_kind="concept_fit",
#             suggested_action="y",
#             target_diagram_id="design-1",
#         )
#         kwargs["on_feedback"](fb, _consistent_result(kwargs["state_hash"]))
#         return _consistent_result(kwargs["state_hash"])

#     tc.board_verifier.request_drift_check = _fake_request_drift_check

#     await _run_drift_check(tc)
#     assert tc.perception_feedback_queue == []
#     stale_events = [e for e in tc.audit.events_for("drift_check") if e.event == "feedback_stale"]
#     assert len(stale_events) == 1


# @pytest.mark.asyncio
# async def test_run_drift_check_callback_drops_when_budget_already_full() -> None:
#     tc = _make_tc(design_ids=["design-1"])
#     tc.original_diagram_claims = {"design-1": "claim"}
#     tc.drift_feedback_budget_used[0] = DRIFT_FEEDBACK_BUDGET_PER_CONCEPT

#     async def _fake_request_drift_check(**kwargs: Any) -> DriftCheckResult:
#         fb = PerceptionFeedback(
#             tool_name="periodic_drift_check",
#             original_claim="x",
#             score=0,
#             issue="x",
#             drift_kind="concept_fit",
#             suggested_action="y",
#             target_diagram_id="design-1",
#         )
#         kwargs["on_feedback"](fb, _consistent_result(kwargs["state_hash"]))
#         return _consistent_result(kwargs["state_hash"])

#     tc.board_verifier.request_drift_check = _fake_request_drift_check

#     await _run_drift_check(tc)
#     assert tc.perception_feedback_queue == []
#     budget_full_events = [
#         e for e in tc.audit.events_for("drift_check") if e.event == "feedback_budget_full"
#     ]
#     assert len(budget_full_events) == 1


# @pytest.mark.asyncio
# async def test_run_drift_check_builds_element_summary_from_original_claims() -> None:
#     tc = _make_tc(design_ids=["design-1", "design-2"])
#     tc.diagram_version = {"design-1": 0, "design-2": 2}
#     tc.original_diagram_claims = {
#         "design-1": "first",
#         "design-2": "second",
#     }

#     captured_summary: list[tuple[str, str, int]] = []

#     async def _fake_request_drift_check(**kwargs: Any) -> DriftCheckResult:
#         captured_summary.extend(kwargs["element_summary"])
#         return _consistent_result(kwargs["state_hash"])

#     tc.board_verifier.request_drift_check = _fake_request_drift_check

#     await _run_drift_check(tc)
#     # Built from original_diagram_claims + diagram_version, version desc.
#     ids = [eid for eid, _, _ in captured_summary]
#     assert ids == ["design-2", "design-1"]
#     assert any(claim == "first" for _, claim, _ in captured_summary)
