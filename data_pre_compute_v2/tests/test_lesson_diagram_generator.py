"""LessonDiagramGenerator tests — doc 19 Phase D.

Strategy mirrors test_lesson_planner.py: inject a fake LLM provider at the
`provider=` seam whose `agenerate_text()` returns canned JSON strings from a
queue. Each test seeds a list of canned responses and asserts call count +
spec contents.

The validator we care about is element_id completeness (every required id is
in BOTH elements[] and dictionary{}). Tests cover the happy path, both
single-axis misses (dict-only, elements-only), the give-up path, the
no-text-content path, an LLM exception, the diagram_id pinning, and the
concurrency semaphore.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from lecture_pipeline_v2.config import LLMConfig, PipelineConfig
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_diagram_generator import (
    LessonDiagramGenerator,
    _validate_required_elements,
)
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_diagram_prompts import (
    LESSON_DIAGRAM_SYSTEM_PROMPT,
)
from lecture_pipeline_v2.llm.base import LLMResponse
from lecture_pipeline_v2.curriculum.lecture_plan.lesson_plan_models import (
    DiagramRequirement,
    ElementRequirement,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _config() -> PipelineConfig:
    return PipelineConfig(
        llm=LLMConfig(api_key="test-key", model="claude-sonnet-4-test")
    )


def _requirement() -> DiagramRequirement:
    return DiagramRequirement(
        diagram_id="train-frame",
        purpose="Show the throw from two reference frames.",
        required_elements=[
            ElementRequirement(
                element_id="vertical-drop",
                role="trajectory",
                description="vertical drop in train frame",
            ),
            ElementRequirement(
                element_id="parabola",
                role="curve",
                description="parabola in ground frame",
            ),
        ],
        presentation_mode="build_up",
    )


# Spec satisfying the two-axis contract: every required id in BOTH lists.
_VALID_SPEC: dict[str, Any] = {
    "title": "Ball in moving train",
    "width": 900,
    "height": 600,
    "elements": [
        {
            "type": "svg_line",
            "id": "vertical-drop",
            "x1": 100,
            "y1": 100,
            "x2": 100,
            "y2": 400,
        },
        {"type": "svg_path", "id": "parabola", "d": "M 50 400 Q 250 100 450 400"},
        {
            "type": "svg_rect",
            "id": "train",
            "x": 30,
            "y": 350,
            "width": 200,
            "height": 100,
        },
    ],
    "dictionary": {
        "vertical-drop": {
            "role": "trajectory",
            "semantic": "ball's vertical drop in train frame",
            "position": "center-left",
            "bounds": [100, 100, 1, 300],
        },
        "parabola": {
            "role": "curve",
            "semantic": "ball's parabolic path in ground frame",
            "position": "center",
            "bounds": [50, 100, 400, 300],
        },
        "train": {
            "role": "frame",
            "semantic": "the moving train",
            "position": "bottom",
            "bounds": [30, 350, 200, 100],
        },
    },
}

# Missing `parabola` from dictionary (still in elements[]) — invalid.
_MISSING_FROM_DICT: dict[str, Any] = {
    **_VALID_SPEC,
    "dictionary": {
        k: v for k, v in _VALID_SPEC["dictionary"].items() if k != "parabola"
    },
}

# Missing `parabola` from elements[] (still in dictionary) — invalid.
_MISSING_FROM_ELEMENTS: dict[str, Any] = {
    **_VALID_SPEC,
    "elements": [el for el in _VALID_SPEC["elements"] if el["id"] != "parabola"],
}


# ─────────────────────────────────────────────────────────────────────────────
# Fake provider (injected at the `provider=` seam)
# ─────────────────────────────────────────────────────────────────────────────


class _FakeTextProvider:
    """LLM provider double. `agenerate_text` pops the next queued item: a str is
    returned as the response content, "" / None models 'no text', and an
    Exception is raised.
    """

    def __init__(self, queue: list[Any]) -> None:
        self._queue = list(queue)
        self.calls: list[dict] = []
        self.last_user_message: str = ""

    async def agenerate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        # System prompt should be Phase D's, not the legacy one.
        assert system_prompt == LESSON_DIAGRAM_SYSTEM_PROMPT
        self.last_user_message = user_prompt
        self.calls.append({"max_tokens": max_tokens})
        if not self._queue:
            raise RuntimeError("test ran out of canned provider responses")
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return LLMResponse(content=item or "", model="fake", usage=None)

    @property
    def create_call_count(self) -> int:
        return len(self.calls)


def _spec_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload)


# ─────────────────────────────────────────────────────────────────────────────
# Direct validator tests (no LLM)
# ─────────────────────────────────────────────────────────────────────────────


def test_validator_accepts_valid_spec() -> None:
    assert _validate_required_elements(_VALID_SPEC, _requirement()) is None


def test_validator_rejects_missing_dictionary_key() -> None:
    err = _validate_required_elements(_MISSING_FROM_DICT, _requirement())
    assert err is not None
    assert "parabola" in err
    assert "dictionary" in err


def test_validator_rejects_missing_elements_id() -> None:
    err = _validate_required_elements(_MISSING_FROM_ELEMENTS, _requirement())
    assert err is not None
    assert "parabola" in err
    assert "elements" in err


def test_validator_rejects_missing_dictionary_field() -> None:
    err = _validate_required_elements(
        {"elements": _VALID_SPEC["elements"]}, _requirement()
    )
    assert err is not None
    assert "dictionary" in err


def test_validator_rejects_missing_elements_field() -> None:
    err = _validate_required_elements(
        {"dictionary": _VALID_SPEC["dictionary"]}, _requirement()
    )
    assert err is not None
    assert "elements" in err


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end async tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_emits_validated_diagram() -> None:
    """Single requirement, single valid response → one Diagram returned."""
    provider = _FakeTextProvider([_spec_text(_VALID_SPEC)])

    gen = LessonDiagramGenerator(_config(), concurrency=1, provider=provider)
    diagrams, report = await gen.generate_for_requirements(
        [("ch1", "topic-1", _requirement())]
    )

    assert len(diagrams) == 1
    assert report.diagrams_generated == 1
    assert report.requirements_seen == 1
    assert provider.create_call_count == 1

    d = diagrams[0]
    # diagram_id is the generated UID, derived from topic_id + the requirement's diagram_id.
    # slugify converts "train-frame" → "train_frame".
    assert "train_frame" in d.diagram_id
    assert d.diagram_id.startswith("diagram:")
    assert d.linked_topic_ids == ["topic-1"]
    assert d.presentation_mode == "build_up"
    # Spec preserved as-is for the renderer.
    assert d.render_data["title"] == "Ball in moving train"


@pytest.mark.asyncio
async def test_retries_when_dictionary_missing_element_id() -> None:
    """First response missing dict entry; second is clean."""
    provider = _FakeTextProvider(
        [_spec_text(_MISSING_FROM_DICT), _spec_text(_VALID_SPEC)]
    )

    gen = LessonDiagramGenerator(_config(), concurrency=1, provider=provider)
    diagrams, report = await gen.generate_for_requirements(
        [("ch1", "topic-1", _requirement())]
    )

    assert len(diagrams) == 1
    assert provider.create_call_count == 2
    assert report.retries_used == 1
    # The retry user message should call out the missing dictionary key.
    assert "parabola" in provider.last_user_message
    assert "RETRY" in provider.last_user_message


@pytest.mark.asyncio
async def test_retries_when_elements_missing_id() -> None:
    """First response missing elements[] entry; second is clean."""
    provider = _FakeTextProvider(
        [_spec_text(_MISSING_FROM_ELEMENTS), _spec_text(_VALID_SPEC)]
    )

    gen = LessonDiagramGenerator(_config(), concurrency=1, provider=provider)
    diagrams, _ = await gen.generate_for_requirements(
        [("ch1", "topic-1", _requirement())]
    )

    assert len(diagrams) == 1
    assert provider.create_call_count == 2
    assert "parabola" in provider.last_user_message


@pytest.mark.asyncio
async def test_gives_up_after_two_validation_failures() -> None:
    """Two consecutive missing-id responses → no diagram emitted."""
    provider = _FakeTextProvider(
        [_spec_text(_MISSING_FROM_DICT), _spec_text(_MISSING_FROM_ELEMENTS)]
    )

    gen = LessonDiagramGenerator(_config(), concurrency=1, provider=provider)
    diagrams, report = await gen.generate_for_requirements(
        [("ch1", "topic-1", _requirement())]
    )

    assert diagrams == []
    assert provider.create_call_count == 2
    assert len(report.failures) == 1
    assert "topic-1::train-frame" in report.failures[0]


@pytest.mark.asyncio
async def test_handles_missing_response_text() -> None:
    """Response with no text → retry; second is clean."""
    provider = _FakeTextProvider(["", _spec_text(_VALID_SPEC)])

    gen = LessonDiagramGenerator(_config(), concurrency=1, provider=provider)
    diagrams, _ = await gen.generate_for_requirements(
        [("ch1", "topic-1", _requirement())]
    )

    assert len(diagrams) == 1
    assert provider.create_call_count == 2


@pytest.mark.asyncio
async def test_catches_unexpected_exception() -> None:
    """Provider raises on both attempts → no diagram, recorded in report."""
    provider = _FakeTextProvider(
        [RuntimeError("simulated API failure"), RuntimeError("again")]
    )

    gen = LessonDiagramGenerator(_config(), concurrency=1, provider=provider)
    diagrams, report = await gen.generate_for_requirements(
        [("ch1", "topic-1", _requirement())]
    )

    assert diagrams == []
    assert provider.create_call_count == 2  # both attempts hit
    assert len(report.failures) == 1


@pytest.mark.asyncio
async def test_pins_diagram_id_against_llm_rename() -> None:
    """LLM emits a spec carrying its own renamed title/id; the resulting
    Diagram.diagram_id is still derived from requirement.diagram_id."""
    renamed_spec = {
        **_VALID_SPEC,
        "title": "totally-different-name",
    }
    provider = _FakeTextProvider([_spec_text(renamed_spec)])

    gen = LessonDiagramGenerator(_config(), concurrency=1, provider=provider)
    diagrams, _ = await gen.generate_for_requirements(
        [("ch1", "topic-1", _requirement())]
    )

    assert len(diagrams) == 1
    # UID embeds the requirement's diagram_id (slugified), NOT the spec's title.
    assert "train_frame" in diagrams[0].diagram_id
    assert "totally" not in diagrams[0].diagram_id  # spec title not embedded


@pytest.mark.asyncio
async def test_concurrency_limited() -> None:
    """Multiple requirements respect the semaphore — at concurrency=1, the
    second provider call cannot start until the first awaits return."""
    # Track the maximum number of in-flight provider calls observed.
    in_flight = 0
    max_in_flight = 0
    barrier = asyncio.Event()

    class _SlowTextProvider:
        def __init__(self) -> None:
            self.create_call_count = 0

        async def agenerate_text(
            self,
            system_prompt: str,
            user_prompt: str,
            *,
            max_tokens: int | None = None,
            temperature: float | None = None,
        ) -> LLMResponse:
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            self.create_call_count += 1
            # Let the test see the in-flight count settle before we resolve.
            await asyncio.sleep(0)
            in_flight -= 1
            barrier.set()
            return LLMResponse(content=_spec_text(_VALID_SPEC), model="fake")

    provider = _SlowTextProvider()
    gen = LessonDiagramGenerator(_config(), concurrency=1, provider=provider)
    requirements = [("ch1", f"topic-{i}", _requirement()) for i in range(3)]
    diagrams, _ = await gen.generate_for_requirements(requirements)

    assert len(diagrams) == 3
    assert provider.create_call_count == 3
    # With concurrency=1, max_in_flight must be 1.
    assert max_in_flight == 1
    assert barrier.is_set()
