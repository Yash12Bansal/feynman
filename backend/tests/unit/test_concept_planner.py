"""Phase 2A — concept planner extension: plan_doubt produces resolution checklist.

The shared `ConceptTeachingPlan` model now carries an optional
`resolution_checklist` field that `plan_doubt` populates and `plan_concept`
leaves empty. The orchestrator gates `resolve_doubt` on every item being done.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from feynman.agent.concept_planner import ConceptTeachingPlan, plan_doubt


def _fake_response(plan_payload: dict):
    """Build a fake AsyncAnthropic response that yields a tool_use block."""
    block = SimpleNamespace(
        type="tool_use",
        name="create_teaching_plan",
        input=plan_payload,
    )
    return SimpleNamespace(content=[block])


PLAN_PAYLOAD = {
    "concept_title": "doubt placeholder",
    "concept_index": -1,
    "opening_hook": "Surface the confusion.",
    "core_analogy": "The shadow always tracks the angle, not the size.",
    "prerequisite_bridge": "Pick up where the ladder left off.",
    "beats": [
        {
            "beat_type": "explain",
            "speech_guidance": "Explain ratio constancy.",
            "target_duration_seconds": 30,
        }
    ],
    "board_pattern": "concept_intro",
    "visual_narrative": "A diagram of similar right triangles.",
    "likely_misconceptions": [],
    "misconception_responses": [],
    "check_questions": [],
    "expected_answers": [],
    "transition_to_next": "Back to the ladder.",
    "resolution_checklist": [
        {
            "description": "show diagram explaining ratio constancy",
            "status": "pending",
            "auto_satisfied_by": ["draw_design_diagram", "draw_scene"],
        },
        {
            "description": "tie the explanation back to the original ladder problem",
            "status": "pending",
            "auto_satisfied_by": ["pin_label_near", "highlight_pulse"],
        },
        {
            "description": "explain why the ratio is angle-dependent",
            "status": "pending",
            "auto_satisfied_by": ["write_step", "write_text"],
        },
    ],
}


@pytest.mark.asyncio
async def test_plan_doubt_produces_checklist(monkeypatch):
    """plan_doubt returns a ConceptTeachingPlan whose resolution_checklist is
    populated with items the LLM produced; auto_satisfied_by uses the
    controlled vocabulary."""

    async def _create(*_args, **_kwargs):
        return _fake_response(PLAN_PAYLOAD)

    fake_client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(side_effect=_create)))

    with patch(
        "feynman.agent.concept_planner.anthropic.AsyncAnthropic",
        return_value=fake_client,
    ):
        result = await plan_doubt(
            "why does sin = opp/hyp?",
            parent_concept="trigonometric ratios",
            board_summary="ladder triangle on slide",
        )

    assert isinstance(result, ConceptTeachingPlan)
    checklist = result.resolution_checklist
    assert len(checklist) == 3

    descriptions = {item.description for item in checklist}
    assert "show diagram explaining ratio constancy" in descriptions

    for item in checklist:
        assert item.status == "pending"
        assert item.auto_satisfied_by, f"Item missing auto_satisfied_by: {item.description}"
        # Controlled vocab — every tool name must be a valid LLM tool we have.
        for tool in item.auto_satisfied_by:
            assert tool in {
                "draw_design_diagram",
                "draw_diagram",
                "draw_scene",
                "pin_label_near",
                "draw_callout",
                "bracket",
                "highlight_pulse",
                "write_section",
                "write_equation",
                "write_step",
                "write_text",
                "show_equation",
            }, f"Unexpected auto_satisfied_by tool: {tool}"
