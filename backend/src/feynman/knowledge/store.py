"""StudentGraphStore — the per-student memory layer over Neo4j.

An INDEPENDENT subgraph (labels: Student, StudySession, AttemptMemory,
DoubtMemory). It never touches curriculum nodes; it references them by id
string only.

Shape:
    (:Student {student_id})
      -[:HAS_SESSION]-> (:StudySession {session_id, subject, chapter_id, local_date, started_at})
        -[:ATTEMPTED]-> (:AttemptMemory {question_id, topic_id, chapter_id, q_text, correct, mode, created_at})
        -[:ASKED]----->  (:DoubtMemory   {topic_id, chapter_id, doubt_text, response, created_at})

A StudySession is one (student, chapter, calendar-day). Its id is DETERMINISTIC
— `make_session_id(student, chapter, local_date)` — so a refresh / new tab / the
worker and the attempt endpoint all resolve to the SAME node with no
coordination (every write is an idempotent MERGE). New day → new id → new
session. This is the anti-spam knob on the WRITE side; `lookback` filters the
READ side. The graph itself is never pruned.

The driver is injected so tests can pass a fake; `connect()` builds one from
settings for production callers. One store instance is meant to live for a
lecture session (the LiveKit worker owns it) and be closed at the end.
"""

from __future__ import annotations

import hashlib
from typing import Any, Literal

import structlog
from neo4j import AsyncGraphDatabase

from feynman.config import settings
from feynman.knowledge.models import AttemptMemory, DoubtMemory, MemoryCard

logger = structlog.get_logger()


def make_session_id(student_id: str, chapter_id: str, local_date: str) -> str:
    """Deterministic id for a (student, chapter, day) study session.

    `chapter_id` is globally unique, so it already pins the subject — we don't
    fold subject in (it can be unknown at session-open and would split the id).
    `local_date` is a YYYY-MM-DD string in the STUDENT's timezone, so "new day"
    matches their midnight, not the server's.
    """
    digest = hashlib.sha256(
        f"{student_id}|{chapter_id}|{local_date}".encode()
    ).hexdigest()
    return digest[:32]


class StudentGraphStore:
    def __init__(self, driver: Any, *, database: str | None = None) -> None:
        self._driver = driver
        self._database = database or settings.neo4j_database

    @classmethod
    def connect(cls) -> StudentGraphStore:
        driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
        )
        return cls(driver)

    async def close(self) -> None:
        await self._driver.close()

    async def ensure_constraints(self) -> None:
        """Idempotent uniqueness constraints on the id keys we MERGE on.

        Without a backing constraint, Neo4j `MERGE` is NOT atomic: two
        concurrent opens of the same session (e.g. a client effect that fires
        twice, or a double-click) each create a node, and every later
        `MATCH (ses {session_id})` then fans out across both — doubling every
        attempt/doubt write. The constraint serialises the MERGE so the second
        caller finds the first's node. Run once at startup."""
        for label, prop in (("Student", "student_id"), ("StudySession", "session_id")):
            await self._run(
                f"CREATE CONSTRAINT {label.lower()}_{prop}_unique IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE",
                {},
            )

    async def _run(self, cypher: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        async with self._driver.session(database=self._database) as session:
            result = await session.run(cypher, params)
            return [record.data() async for record in result]

    async def start_session(
        self,
        *,
        student_id: str,
        session_id: str,
        subject: str,
        chapter_id: str,
        local_date: str,
        started_at: int,
    ) -> None:
        """Open the (student, chapter, day) study session, creating the Student
        on first sight. Idempotent: the deterministic session_id means a refresh
        / new tab / the worker all MERGE onto the same node, written once."""
        # ON CREATE SET → the session's identity attributes are written once,
        # at first sight, and never moved again (append-only in spirit).
        await self._run(
            """
            MERGE (s:Student {student_id: $student_id})
            MERGE (ses:StudySession {session_id: $session_id})
            ON CREATE SET ses.subject = $subject,
                          ses.chapter_id = $chapter_id,
                          ses.local_date = $local_date,
                          ses.started_at = $started_at
            MERGE (s)-[:HAS_SESSION]->(ses)
            """,
            {
                "student_id": student_id,
                "session_id": session_id,
                "subject": subject,
                "chapter_id": chapter_id,
                "local_date": local_date,
                "started_at": started_at,
            },
        )

    async def complete_session(self, *, session_id: str, ended_at: int) -> None:
        """Stamp a session finished (player reached the end). Optional metadata
        — the memory card never depends on it; an unfinished sitting still
        keeps its doubts + attempts.
        """
        await self._run(
            "MATCH (ses:StudySession {session_id: $session_id}) "
            "SET ses.ended_at = $ended_at",
            {"session_id": session_id, "ended_at": ended_at},
        )

    async def record_attempt(
        self,
        *,
        session_id: str,
        question_id: str,
        topic_id: str,
        q_text: str,
        options: list[str],
        solution: str,
        solution_steps: list[str],
        correct: bool,
        mode: Literal["mcq", "subjective"],
        created_at: int,
    ) -> None:
        await self._run(
            """
            MATCH (ses:StudySession {session_id: $session_id})
            CREATE (a:AttemptMemory {
                question_id: $question_id, topic_id: $topic_id,
                chapter_id: ses.chapter_id, q_text: $q_text,
                options: $options, solution: $solution,
                solution_steps: $solution_steps,
                correct: $correct, mode: $mode, created_at: $created_at
            })
            MERGE (ses)-[:ATTEMPTED]->(a)
            """,
            {
                "session_id": session_id,
                "question_id": question_id,
                "topic_id": topic_id,
                "q_text": q_text,
                "options": options,
                "solution": solution,
                "solution_steps": solution_steps,
                "correct": correct,
                "mode": mode,
                "created_at": created_at,
            },
        )

    async def record_doubt(
        self,
        *,
        session_id: str,
        topic_id: str,
        doubt_text: str,
        response: str,
        created_at: int,
    ) -> None:
        await self._run(
            """
            MATCH (ses:StudySession {session_id: $session_id})
            CREATE (d:DoubtMemory {
                topic_id: $topic_id, chapter_id: ses.chapter_id,
                doubt_text: $doubt_text,
                response: $response, created_at: $created_at
            })
            MERGE (ses)-[:ASKED]->(d)
            """,
            {
                "session_id": session_id,
                "topic_id": topic_id,
                "doubt_text": doubt_text,
                "response": response,
                "created_at": created_at,
            },
        )

    async def get_memory_card(
        self,
        *,
        student_id: str,
        chapter_id: str,
        lookback_sessions: int | None = None,
        exclude_session_id: str | None = None,
    ) -> MemoryCard:
        """Auto-pop card: incorrect attempts + doubts from this student's last N
        study-days on this chapter. N defaults to `memory_lookback_sessions`.

        `exclude_session_id` drops TODAY's session from the window — so the card
        always reflects PRIOR days, even on a mid-lecture refresh when today's
        session already exists in the graph.
        """
        n = lookback_sessions or settings.memory_lookback_sessions
        rows = await self._run(
            """
            MATCH (s:Student {student_id: $student_id})
                  -[:HAS_SESSION]->(ses:StudySession {chapter_id: $chapter_id})
            WHERE $exclude IS NULL OR ses.session_id <> $exclude
            WITH ses ORDER BY ses.started_at DESC LIMIT $n
            OPTIONAL MATCH (ses)-[:ATTEMPTED]->(a:AttemptMemory {correct: false})
            OPTIONAL MATCH (ses)-[:ASKED]->(d:DoubtMemory)
            RETURN collect(DISTINCT a) AS attempts,
                   collect(DISTINCT d) AS doubts,
                   count(DISTINCT ses) AS sessions_covered
            """,
            {
                "student_id": student_id,
                "chapter_id": chapter_id,
                "n": n,
                "exclude": exclude_session_id,
            },
        )
        return self._card(student_id, chapter_id, rows[0] if rows else None)

    async def get_chapter_memory(
        self, *, student_id: str, chapter_id: str
    ) -> MemoryCard:
        """Full-chapter "weakness" card — every study-day on this chapter,
        INCLUDING today. Backs the "important points of this chapter, just for
        you" button (an explicit pull, so no exclude / no lookback cap)."""
        rows = await self._run(
            """
            MATCH (s:Student {student_id: $student_id})
                  -[:HAS_SESSION]->(ses:StudySession {chapter_id: $chapter_id})
            OPTIONAL MATCH (ses)-[:ATTEMPTED]->(a:AttemptMemory {correct: false})
            OPTIONAL MATCH (ses)-[:ASKED]->(d:DoubtMemory)
            RETURN collect(DISTINCT a) AS attempts,
                   collect(DISTINCT d) AS doubts,
                   count(DISTINCT ses) AS sessions_covered
            """,
            {"student_id": student_id, "chapter_id": chapter_id},
        )
        return self._card(student_id, chapter_id, rows[0] if rows else None)

    async def get_global_memory(
        self, *, student_id: str, limit: int | None = None
    ) -> MemoryCard:
        """User-level card — the student's most recent mistakes + doubts across
        EVERY chapter, newest first, capped. Backs the home-screen / on-login
        review. Each item carries its own `chapter_id` for labelling."""
        lim = limit or settings.memory_global_limit
        rows = await self._run(
            """
            MATCH (s:Student {student_id: $student_id})
            OPTIONAL MATCH (s)-[:HAS_SESSION]->()-[:ATTEMPTED]->(a:AttemptMemory {correct: false})
            WITH s, a ORDER BY a.created_at DESC
            WITH s, collect(a)[0..$lim] AS attempts
            OPTIONAL MATCH (s)-[:HAS_SESSION]->()-[:ASKED]->(d:DoubtMemory)
            WITH attempts, d ORDER BY d.created_at DESC
            RETURN attempts, collect(d)[0..$lim] AS doubts, 0 AS sessions_covered
            """,
            {"student_id": student_id, "lim": lim},
        )
        # Global card spans many chapters → top-level chapter_id is "".
        return self._card(student_id, "", rows[0] if rows else None, sort=False)

    @staticmethod
    def _card(
        student_id: str,
        chapter_id: str,
        row: dict[str, Any] | None,
        *,
        sort: bool = True,
    ) -> MemoryCard:
        """Shape a query row into a MemoryCard. `sort=True` re-sorts newest-first
        (the per-session collects aren't ordered); the global query already
        orders in Cypher, so it passes sort=False."""
        if row is None:
            return MemoryCard(student_id=student_id, chapter_id=chapter_id)
        attempts = [
            AttemptMemory(**a) for a in (row.get("attempts") or []) if a is not None
        ]
        doubts = [DoubtMemory(**d) for d in (row.get("doubts") or []) if d is not None]
        if sort:
            attempts.sort(key=lambda x: x.created_at, reverse=True)
            doubts.sort(key=lambda x: x.created_at, reverse=True)
        return MemoryCard(
            student_id=student_id,
            chapter_id=chapter_id,
            incorrect_attempts=attempts,
            doubts=doubts,
            sessions_covered=int(row.get("sessions_covered") or 0),
        )
