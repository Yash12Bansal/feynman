"""Parity + behavior guards for the doubt-path diagram-template catalog.

The catalog MUST stay in lock-step with the frontend registry — the parity
test parses the `.ts` template files so an id added on one side fails CI until
it's mirrored on the other. A drifted id would render a blank doubt slide with
no error (the #1 template risk), so this guard is load-bearing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from feynman.agent.doubt_resolution import diagram_templates as dt
from feynman.agent.doubt_resolution.models import ResolutionPlan, TemplateDiagram

_FRONTEND_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[3] / "frontend/src/engine/whiteboard/diagram-templates"
)


def _frontend_concept_ids() -> set[str]:
    ids: set[str] = set()
    for ts in _FRONTEND_TEMPLATES_DIR.glob("*.ts"):
        if ts.name in {"types.ts", "registry.ts"} or ts.name.endswith(".test.ts"):
            continue
        for m in re.finditer(r'conceptId:\s*"([^"]+)"', ts.read_text()):
            ids.add(m.group(1))
    return ids


@pytest.mark.skipif(
    not _FRONTEND_TEMPLATES_DIR.exists(), reason="frontend not present in this checkout"
)
def test_catalog_matches_frontend_registry_exactly() -> None:
    frontend = _frontend_concept_ids()
    assert frontend, "found no frontend template conceptIds — path wrong?"
    assert set(dt.TEMPLATE_CONCEPT_IDS) == frontend, (
        f"drift — backend-only={set(dt.TEMPLATE_CONCEPT_IDS) - frontend}, "
        f"frontend-only={frontend - set(dt.TEMPLATE_CONCEPT_IDS)}"
    )


def test_is_known_and_prompt_block() -> None:
    assert dt.is_known("right-triangle-trig")
    assert not dt.is_known("bogus")
    block = dt.format_templates_for_prompt()
    for t in dt.list_templates():
        assert t.concept_id in block, f"{t.concept_id} missing from prompt block"
    assert "theta" in block  # a parameter surfaces for the planner


def test_template_directive_validates_into_plan() -> None:
    plan = ResolutionPlan.model_validate(
        {
            "classification": {"type": "local_clarification"},
            "beats": [
                {
                    "narration_text": "The angle of elevation is the key.",
                    "diagram": {
                        "mode": "template",
                        "concept_id": "right-triangle-trig",
                        "params": {"theta": 30},
                    },
                }
            ]
        }
    )
    d = plan.beats[0].diagram
    assert isinstance(d, TemplateDiagram)
    assert d.concept_id == "right-triangle-trig" and d.params == {"theta": 30}
