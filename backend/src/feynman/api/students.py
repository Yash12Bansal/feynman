"""Student endpoints — study-session lifecycle + the personalised memory cards.

A StudySession is one (student, chapter, calendar-day) with a DETERMINISTIC id
(`make_session_id`). Opening the same chapter again the same day — refresh, new
tab, the doubt worker — all resolve to the SAME session; a new day starts a new
one. So sessions don't multiply per refresh (anti-spam), and the next-DAY memory
card naturally shows the prior day's mistakes.

Three card surfaces:
  GET /memory-card    → auto-pop: last N study-days on a chapter, today excluded.
  GET /chapter-memory → full chapter history incl. today (the "weakness" button).
  GET /global-memory  → user-level: recent mistakes/doubts across every chapter.
"""

import time
from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel

from feynman.knowledge import MemoryCard, StudentGraphStore, make_session_id

router = APIRouter()


def _now_ms() -> int:
    return int(time.time() * 1000)


class StartSessionRequest(BaseModel):
    chapter_id: str
    subject: str = ""
    # YYYY-MM-DD in the STUDENT's timezone (computed client-side). Defines the
    # session's day boundary; empty falls back to the server's UTC date.
    local_date: str = ""


class StartSessionResponse(BaseModel):
    session_id: str
    started_at: int


@router.post("/{student_id}/sessions", response_model=StartSessionResponse)
async def start_study_session(
    student_id: str, body: StartSessionRequest
) -> StartSessionResponse:
    """Resolve today's study session for a chapter (idempotent MERGE). The
    deterministic session_id is held by the frontend and threaded to the doubt
    worker (room metadata) + the attempt endpoint, so everything that day shares
    one session — and a refresh resolves to the same one."""
    local_date = body.local_date or datetime.now(UTC).strftime("%Y-%m-%d")
    session_id = make_session_id(student_id, body.chapter_id, local_date)
    started_at = _now_ms()
    store = StudentGraphStore.connect()
    try:
        await store.start_session(
            student_id=student_id,
            session_id=session_id,
            subject=body.subject,
            chapter_id=body.chapter_id,
            local_date=local_date,
            started_at=started_at,
        )
    finally:
        await store.close()
    return StartSessionResponse(session_id=session_id, started_at=started_at)


@router.post("/{student_id}/sessions/{session_id}/complete")
async def complete_study_session(student_id: str, session_id: str) -> dict[str, bool]:
    """Mark a session finished (player reached the chapter's end). Best-effort
    metadata — never required for the memory card."""
    _ = student_id  # session_id is globally unique; student scoping not needed here
    store = StudentGraphStore.connect()
    try:
        await store.complete_session(session_id=session_id, ended_at=_now_ms())
    finally:
        await store.close()
    return {"ok": True}


@router.get("/{student_id}/memory-card", response_model=MemoryCard)
async def get_memory_card(
    student_id: str,
    chapter_id: str,
    lookback: int | None = None,
    exclude: str | None = None,
) -> MemoryCard:
    """Revision card for a student on one chapter: the questions they got
    wrong + the doubts they raised, across their last N sessions.

    `lookback` defaults to `settings.memory_lookback_sessions` (2). `exclude`
    is the current sitting's session_id, dropped from the window so the card
    only shows PRIOR sessions. Returns an empty card (never errors) when the
    student has no history for the chapter.
    """
    store = StudentGraphStore.connect()
    try:
        return await store.get_memory_card(
            student_id=student_id,
            chapter_id=chapter_id,
            lookback_sessions=lookback,
            exclude_session_id=exclude,
        )
    finally:
        await store.close()


@router.get("/{student_id}/chapter-memory", response_model=MemoryCard)
async def get_chapter_memory(student_id: str, chapter_id: str) -> MemoryCard:
    """Full-chapter "weakness" card — every study-day on this chapter, INCLUDING
    today. Backs the "important points of this chapter, just for you" button: an
    explicit pull, so nothing is excluded and there's no lookback cap. Returns an
    empty card (never errors) for a first-time visitor."""
    store = StudentGraphStore.connect()
    try:
        return await store.get_chapter_memory(
            student_id=student_id, chapter_id=chapter_id
        )
    finally:
        await store.close()


@router.get("/{student_id}/global-memory", response_model=MemoryCard)
async def get_global_memory(student_id: str, limit: int | None = None) -> MemoryCard:
    """User-level card — the student's most recent mistakes + doubts across every
    chapter, newest first, capped (`memory_global_limit`, default 8). Backs the
    home-screen / on-login review. Each item carries its own chapter_id."""
    store = StudentGraphStore.connect()
    try:
        return await store.get_global_memory(student_id=student_id, limit=limit)
    finally:
        await store.close()
