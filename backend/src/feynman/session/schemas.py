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
