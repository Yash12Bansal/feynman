"""StudentGraphStore tests — fake async Neo4j driver, no network.

The fake records every (cypher, params) the store runs and returns canned
rows for reads. We assert the write methods emit the right parameters and
that get_memory_card shapes rows into a MemoryCard correctly.
"""

from __future__ import annotations

from typing import Any

import pytest

from feynman.knowledge import MemoryCard, StudentGraphStore, make_session_id

# ── Fake async Neo4j driver ─────────────────────────────────────────────────


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = list(rows)

    def __aiter__(self) -> _FakeResult:
        return self

    async def __anext__(self) -> Any:
        if not self._rows:
            raise StopAsyncIteration
        row = self._rows.pop(0)
        return _FakeRecord(row)


class _FakeRecord:
    def __init__(self, row: dict[str, Any]) -> None:
        self._row = row

    def data(self) -> dict[str, Any]:
        return self._row


class _FakeSession:
    def __init__(self, driver: _FakeDriver) -> None:
        self._driver = driver

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def run(self, cypher: str, params: dict[str, Any]) -> _FakeResult:
        self._driver.calls.append((cypher, params))
        # Reads (get_memory_card) consume the queued rows; writes return none.
        if "RETURN" in cypher and self._driver.read_rows is not None:
            return _FakeResult(self._driver.read_rows)
        return _FakeResult([])


class _FakeDriver:
    def __init__(self, read_rows: list[dict[str, Any]] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.read_rows = read_rows
        self.closed = False

    def session(self, *, database: str | None = None) -> _FakeSession:
        return _FakeSession(self)

    async def close(self) -> None:
        self.closed = True


def _store(read_rows: list[dict[str, Any]] | None = None) -> tuple[StudentGraphStore, _FakeDriver]:
    driver = _FakeDriver(read_rows=read_rows)
    return StudentGraphStore(driver, database="neo4j"), driver


# ── Writes ──────────────────────────────────────────────────────────────────


def test_make_session_id_is_deterministic_and_day_scoped() -> None:
    a = make_session_id("u1", "ch13", "2026-06-13")
    # Same (student, chapter, day) → same id (refresh / new tab / worker agree).
    assert a == make_session_id("u1", "ch13", "2026-06-13")
    # New day → new id.
    assert a != make_session_id("u1", "ch13", "2026-06-14")
    # Different chapter or student → new id.
    assert a != make_session_id("u1", "ch99", "2026-06-13")
    assert a != make_session_id("u2", "ch13", "2026-06-13")


@pytest.mark.asyncio
async def test_start_session_merges_student_and_session() -> None:
    store, driver = _store()
    await store.start_session(
        student_id="u1", session_id="s1", subject="physics",
        chapter_id="ch13", local_date="2026-06-13", started_at=1000,
    )
    cypher, params = driver.calls[-1]
    assert "MERGE (s:Student {student_id: $student_id})" in cypher
    assert params["student_id"] == "u1"
    assert params["chapter_id"] == "ch13"
    assert params["local_date"] == "2026-06-13"
    assert params["started_at"] == 1000


@pytest.mark.asyncio
async def test_record_attempt_passes_all_fields() -> None:
    store, driver = _store()
    await store.record_attempt(
        session_id="s1", question_id="q1", topic_id="t1", q_text="Why?",
        options=["A. yes", "B. no"], solution="B", solution_steps=["Inertia keeps it moving."],
        correct=False, mode="mcq", created_at=2000,
    )
    cypher, params = driver.calls[-1]
    assert "CREATE (a:AttemptMemory" in cypher
    assert params["correct"] is False
    assert params["mode"] == "mcq"
    assert params["q_text"] == "Why?"
    assert params["options"] == ["A. yes", "B. no"]
    assert params["solution"] == "B"
    assert params["solution_steps"] == ["Inertia keeps it moving."]


@pytest.mark.asyncio
async def test_record_doubt_passes_all_fields() -> None:
    store, driver = _store()
    await store.record_doubt(
        session_id="s1", topic_id="t1", doubt_text="huh?",
        response="here's why", created_at=3000,
    )
    cypher, params = driver.calls[-1]
    assert "CREATE (d:DoubtMemory" in cypher
    assert params["doubt_text"] == "huh?"
    assert params["response"] == "here's why"


# ── Read: memory card ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_memory_card_shapes_rows() -> None:
    rows = [
        {
            "attempts": [
                {
                    "question_id": "q1", "topic_id": "t1", "q_text": "Q1",
                    "correct": False, "mode": "mcq", "created_at": 50,
                },
                {
                    "question_id": "q2", "topic_id": "t1", "q_text": "Q2",
                    "correct": False, "mode": "subjective", "created_at": 90,
                },
            ],
            "doubts": [
                {"topic_id": "t1", "doubt_text": "d?", "response": "r", "created_at": 70},
            ],
            "sessions_covered": 2,
        }
    ]
    store, driver = _store(read_rows=rows)
    card = await store.get_memory_card(student_id="u1", chapter_id="ch13", lookback_sessions=2)

    assert isinstance(card, MemoryCard)
    assert card.sessions_covered == 2
    assert not card.is_empty
    # Newest-first ordering.
    assert [a.question_id for a in card.incorrect_attempts] == ["q2", "q1"]
    assert card.doubts[0].doubt_text == "d?"
    # lookback param flowed into the query.
    _cypher, params = driver.calls[-1]
    assert params["n"] == 2


@pytest.mark.asyncio
async def test_get_memory_card_empty_when_no_rows() -> None:
    store, _driver = _store(read_rows=[{"attempts": [], "doubts": [], "sessions_covered": 0}])
    card = await store.get_memory_card(student_id="u1", chapter_id="ch13")
    assert card.is_empty
    assert card.sessions_covered == 0


@pytest.mark.asyncio
async def test_get_memory_card_passes_exclude_session() -> None:
    """The current sitting's session_id is forwarded so the query drops it."""
    store, driver = _store(read_rows=[{"attempts": [], "doubts": [], "sessions_covered": 0}])
    await store.get_memory_card(
        student_id="u1", chapter_id="ch13", exclude_session_id="cur-sess"
    )
    cypher, params = driver.calls[-1]
    assert params["exclude"] == "cur-sess"
    assert "ses.session_id <> $exclude" in cypher


@pytest.mark.asyncio
async def test_get_chapter_memory_no_exclude_no_lookback() -> None:
    """Full-chapter pull: every session, no exclude clause, no LIMIT on sessions."""
    rows = [{"attempts": [], "doubts": [], "sessions_covered": 3}]
    store, driver = _store(read_rows=rows)
    card = await store.get_chapter_memory(student_id="u1", chapter_id="ch13")
    assert card.sessions_covered == 3
    cypher, params = driver.calls[-1]
    assert "<> $exclude" not in cypher  # current session is INCLUDED here
    assert params["chapter_id"] == "ch13"
    assert "exclude" not in params


@pytest.mark.asyncio
async def test_get_global_memory_spans_all_chapters_and_caps() -> None:
    rows = [
        {
            "attempts": [
                {
                    "question_id": "q1", "topic_id": "t1", "chapter_id": "chA",
                    "q_text": "Q1", "correct": False, "mode": "mcq", "created_at": 90,
                }
            ],
            "doubts": [
                {"topic_id": "t2", "chapter_id": "chB", "doubt_text": "d?",
                 "response": "r", "created_at": 80},
            ],
            "sessions_covered": 0,
        }
    ]
    store, driver = _store(read_rows=rows)
    card = await store.get_global_memory(student_id="u1", limit=8)
    # Items carry their own chapter_id; the card itself is chapter-agnostic.
    assert card.chapter_id == ""
    assert card.incorrect_attempts[0].chapter_id == "chA"
    assert card.doubts[0].chapter_id == "chB"
    cypher, params = driver.calls[-1]
    assert params["lim"] == 8
    assert "[0..$lim]" in cypher  # cap applied in Cypher


@pytest.mark.asyncio
async def test_ensure_constraints_emits_uniqueness_for_id_keys() -> None:
    """The uniqueness constraints are what make MERGE atomic (no duplicate
    Student/StudySession nodes under a double-fired client effect)."""
    store, driver = _store()
    await store.ensure_constraints()
    cyphers = " ".join(c for c, _ in driver.calls)
    assert "Student" in cyphers and "student_id IS UNIQUE" in cyphers
    assert "StudySession" in cyphers and "session_id IS UNIQUE" in cyphers
    assert "IF NOT EXISTS" in cyphers  # idempotent


@pytest.mark.asyncio
async def test_close_closes_driver() -> None:
    store, driver = _store()
    await store.close()
    assert driver.closed is True
