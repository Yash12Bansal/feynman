"""LessonDiagramGenerator tests — doc 19 Phase D.

Strategy mirrors test_lesson_planner.py: monkeypatch `anthropic.AsyncAnthropic`
with a fake whose `messages.create()` returns canned text-block responses.
Each test seeds a list of canned responses and asserts call count + spec
contents.

The validator we care about is element_id completeness (every required id is
in BOTH elements[] and dictionary{}). Tests cover the happy path, both
single-axis misses (dict-only, elements-only), the give-up path, the
no-text-content path, an LLM exception, the diagram_id pinning, and the
concurrency semaphore.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
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
# Fake Anthropic client harness — mirrors test_lesson_planner.py
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class _FakeTextBlock:
    """Mimics anthropic.types.TextBlock shape."""

    type: str
    text: str


@dataclass
class _FakeResponse:
    content: list[_FakeTextBlock]


class _FakeMessages:
    def __init__(self, queue: list[_FakeResponse]) -> None:
        self._queue = queue
        self.create_call_count = 0
        self.last_user_message: str = ""

    async def create(self, **kwargs: Any) -> _FakeResponse:
        # System prompt should be Phase D's, not the legacy one.
        assert kwargs.get("system") == LESSON_DIAGRAM_SYSTEM_PROMPT
        # Capture the user message so tests can introspect retry feedback.
        messages = kwargs.get("messages") or []
        if messages:
            self.last_user_message = messages[0].get("content", "")
        self.create_call_count += 1
        if not self._queue:
            raise RuntimeError("test ran out of canned Anthropic responses")
        return self._queue.pop(0)


class _FakeAnthropicClient:
    def __init__(self, *, api_key: str | None = None) -> None:
        self.api_key = api_key
        self.messages = _CURRENT_FAKE_MESSAGES


_CURRENT_FAKE_MESSAGES: _FakeMessages | None = None


def _install_fake(
    monkeypatch: pytest.MonkeyPatch, responses: list[_FakeResponse]
) -> _FakeMessages:
    global _CURRENT_FAKE_MESSAGES
    _CURRENT_FAKE_MESSAGES = _FakeMessages(responses)
    monkeypatch.setattr(
        "lecture_pipeline_v2.curriculum.lecture_plan.lesson_diagram_generator.anthropic.AsyncAnthropic",
        _FakeAnthropicClient,
    )
    return _CURRENT_FAKE_MESSAGES


def _text_response(payload: dict[str, Any]) -> _FakeResponse:
    import json as _json

    return _FakeResponse(
        content=[_FakeTextBlock(type="text", text=_json.dumps(payload))]
    )


def _empty_response() -> _FakeResponse:
    return _FakeResponse(content=[])


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
async def test_happy_path_emits_validated_diagram(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Single requirement, single valid response → one Diagram returned."""
    messages = _install_fake(monkeypatch, [_text_response(_VALID_SPEC)])

    gen = LessonDiagramGenerator(_config(), concurrency=1)
    diagrams, report = await gen.generate_for_requirements(
        [("ch1", "topic-1", _requirement())]
    )

    assert len(diagrams) == 1
    assert report.diagrams_generated == 1
    assert report.requirements_seen == 1
    assert messages.create_call_count == 1

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
async def test_retries_when_dictionary_missing_element_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First response missing dict entry; second is clean."""
    messages = _install_fake(
        monkeypatch,
        [_text_response(_MISSING_FROM_DICT), _text_response(_VALID_SPEC)],
    )

    gen = LessonDiagramGenerator(_config(), concurrency=1)
    diagrams, report = await gen.generate_for_requirements(
        [("ch1", "topic-1", _requirement())]
    )

    assert len(diagrams) == 1
    assert messages.create_call_count == 2
    assert report.retries_used == 1
    # The retry user message should call out the missing dictionary key.
    assert "parabola" in messages.last_user_message
    assert "RETRY" in messages.last_user_message


@pytest.mark.asyncio
async def test_retries_when_elements_missing_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First response missing elements[] entry; second is clean."""
    messages = _install_fake(
        monkeypatch,
        [_text_response(_MISSING_FROM_ELEMENTS), _text_response(_VALID_SPEC)],
    )

    gen = LessonDiagramGenerator(_config(), concurrency=1)
    diagrams, _ = await gen.generate_for_requirements(
        [("ch1", "topic-1", _requirement())]
    )

    assert len(diagrams) == 1
    assert messages.create_call_count == 2
    assert "parabola" in messages.last_user_message


@pytest.mark.asyncio
async def test_gives_up_after_two_validation_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two consecutive missing-id responses → no diagram emitted."""
    messages = _install_fake(
        monkeypatch,
        [
            _text_response(_MISSING_FROM_DICT),
            _text_response(_MISSING_FROM_ELEMENTS),
        ],
    )

    gen = LessonDiagramGenerator(_config(), concurrency=1)
    diagrams, report = await gen.generate_for_requirements(
        [("ch1", "topic-1", _requirement())]
    )

    assert diagrams == []
    assert messages.create_call_count == 2
    assert len(report.failures) == 1
    assert "topic-1::train-frame" in report.failures[0]


@pytest.mark.asyncio
async def test_handles_missing_response_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Response with no text block → retry; second is clean."""
    messages = _install_fake(
        monkeypatch,
        [_empty_response(), _text_response(_VALID_SPEC)],
    )

    gen = LessonDiagramGenerator(_config(), concurrency=1)
    diagrams, _ = await gen.generate_for_requirements(
        [("ch1", "topic-1", _requirement())]
    )

    assert len(diagrams) == 1
    assert messages.create_call_count == 2


@pytest.mark.asyncio
async def test_catches_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Anthropic API raises on both attempts → no diagram, recorded in report."""

    class _ExplodingMessages:
        def __init__(self) -> None:
            self.create_call_count = 0

        async def create(self, **kwargs: Any) -> Any:
            self.create_call_count += 1
            raise RuntimeError("simulated API failure")

    global _CURRENT_FAKE_MESSAGES
    exploding = _ExplodingMessages()
    _CURRENT_FAKE_MESSAGES = exploding  # type: ignore[assignment]
    monkeypatch.setattr(
        "lecture_pipeline_v2.curriculum.lecture_plan.lesson_diagram_generator.anthropic.AsyncAnthropic",
        _FakeAnthropicClient,
    )

    gen = LessonDiagramGenerator(_config(), concurrency=1)
    diagrams, report = await gen.generate_for_requirements(
        [("ch1", "topic-1", _requirement())]
    )

    assert diagrams == []
    assert exploding.create_call_count == 2  # both attempts hit
    assert len(report.failures) == 1


@pytest.mark.asyncio
async def test_pins_diagram_id_against_llm_rename(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM emits a spec carrying its own renamed title/id; the resulting
    Diagram.diagram_id is still derived from requirement.diagram_id."""
    renamed_spec = {
        **_VALID_SPEC,
        "title": "totally-different-name",
    }
    _install_fake(monkeypatch, [_text_response(renamed_spec)])

    gen = LessonDiagramGenerator(_config(), concurrency=1)
    diagrams, _ = await gen.generate_for_requirements(
        [("ch1", "topic-1", _requirement())]
    )

    assert len(diagrams) == 1
    # UID embeds the requirement's diagram_id (slugified), NOT the spec's title.
    assert "train_frame" in diagrams[0].diagram_id
    assert "totally" not in diagrams[0].diagram_id  # spec title not embedded


@pytest.mark.asyncio
async def test_concurrency_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    """Multiple requirements respect the semaphore — at concurrency=1, the
    second create() call cannot start until the first awaits return."""
    # Track the maximum number of in-flight create() calls observed.
    in_flight = 0
    max_in_flight = 0
    barrier = asyncio.Event()

    class _SlowMessages:
        def __init__(self) -> None:
            self.create_call_count = 0

        async def create(self, **kwargs: Any) -> _FakeResponse:
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            self.create_call_count += 1
            # Let the test see the in-flight count settle before we resolve.
            await asyncio.sleep(0)
            in_flight -= 1
            barrier.set()
            return _text_response(_VALID_SPEC)

    global _CURRENT_FAKE_MESSAGES
    slow = _SlowMessages()
    _CURRENT_FAKE_MESSAGES = slow  # type: ignore[assignment]
    monkeypatch.setattr(
        "lecture_pipeline_v2.curriculum.lecture_plan.lesson_diagram_generator.anthropic.AsyncAnthropic",
        _FakeAnthropicClient,
    )

    gen = LessonDiagramGenerator(_config(), concurrency=1)
    requirements = [("ch1", f"topic-{i}", _requirement()) for i in range(3)]
    diagrams, _ = await gen.generate_for_requirements(requirements)

    assert len(diagrams) == 3
    assert slow.create_call_count == 3
    # With concurrency=1, max_in_flight must be 1.
    assert max_in_flight == 1
    assert barrier.is_set()
