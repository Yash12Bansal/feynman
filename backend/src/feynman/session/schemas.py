"""Pydantic schemas for teaching sessions."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel

from feynman.agent.states import TeachingState
from feynman.common.types import Subject


class SessionStatus(StrEnum):
    """Lifecycle status of a teaching session (not the teaching state)."""

    PENDING = "pending"
    ACTIVE = "active"
    ENDED = "ended"


class SessionCreate(BaseModel):
    """Input for creating a new teaching session."""

    subject: Subject | None = None
    topic: str = ""
    grade_level: str = ""
    # When set, the session is bound to a precomputed lecture chapter and the
    # frontend lands in immersive LectureViewer mode. The agent worker stays
    # connected to the room but silent; doubts are handled by the doubt-
    # resolution pipeline (Phase 3+).
    lecture_chapter_id: str | None = None
    persona_id: str | None = None


class SessionInfo(BaseModel):
    """Full session data for API responses and internal use."""

    id: UUID
    room_name: str
    subject: Subject | None
    status: SessionStatus
    teaching_state: TeachingState
    branch_depth: int
    created_at: datetime
    updated_at: datetime
    ended_at: datetime | None


class CreateSessionResponse(BaseModel):
    """Response from POST /sessions — includes LiveKit connection details."""

    session_id: str
    token: str
    livekit_url: str
    room_name: str
    # Echoed back so the frontend can render the immersive LectureViewer when
    # the caller supplied a chapter id.
    lecture_chapter_id: str | None = None
    persona_id: str | None = None
