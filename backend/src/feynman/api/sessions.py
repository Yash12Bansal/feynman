"""Session management endpoints — create sessions and generate LiveKit tokens."""

import json
from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException, Request
from livekit.api import AccessToken, LiveKitAPI, VideoGrants
from livekit.protocol.room import CreateRoomRequest

from feynman.common.exceptions import SessionNotFoundError
from feynman.config import settings
from feynman.session import (
    CreateSessionResponse,
    SessionCreate,
    SessionInfo,
    SessionManager,
)

logger = structlog.get_logger()
router = APIRouter()


def _get_manager(request: Request) -> SessionManager:
    return request.app.state.session_manager


def _create_livekit_token(room_name: str, identity: str) -> str:
    return (
        AccessToken(api_key=settings.livekit_api_key, api_secret=settings.livekit_api_secret)
        .with_identity(identity)
        .with_name("Classroom Screen")
        .with_grants(
            VideoGrants(
                room=room_name,
                room_join=True,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .to_jwt()
    )


async def _create_livekit_room(
    room_name: str,
    topic: str,
    subject: str | None,
    grade_level: str,
    lecture_chapter_id: str | None,
    student_id: str | None,
    study_session_id: str | None,
) -> None:
    """Pre-create the LiveKit room with metadata so the worker can read the topic."""
    metadata = {}
    if topic:
        metadata["topic"] = topic
    if subject:
        metadata["subject"] = subject
    if grade_level:
        metadata["grade_level"] = grade_level
    if lecture_chapter_id:
        metadata["lecture_chapter_id"] = lecture_chapter_id
    if student_id:
        metadata["student_id"] = student_id
    if study_session_id:
        metadata["study_session_id"] = study_session_id

    if not metadata:
        return

    lk = LiveKitAPI(
        url=settings.livekit_url,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
    )
    try:
        await lk.room.create_room(CreateRoomRequest(name=room_name, metadata=json.dumps(metadata)))
        logger.info("livekit.room_created", room_name=room_name, metadata=metadata)
    finally:
        await lk.aclose()


@router.post("", response_model=CreateSessionResponse)
async def create_session(
    request: Request,
    body: SessionCreate | None = None,
) -> CreateSessionResponse:
    manager = _get_manager(request)
    session = await manager.create_session(body)

    # Pre-create LiveKit room with topic metadata for the worker to read
    topic = body.topic if body else ""
    subject = body.subject.value if body and body.subject else None
    grade_level = body.grade_level if body else ""
    lecture_chapter_id = body.lecture_chapter_id if body else None
    student_id = body.student_id if body else None
    study_session_id = body.study_session_id if body else None
    await _create_livekit_room(
        session.room_name, topic, subject, grade_level, lecture_chapter_id,
        student_id, study_session_id,
    )

    token = _create_livekit_token(
        room_name=session.room_name,
        identity=f"classroom-{session.id!s:.8}",
    )

    return CreateSessionResponse(
        session_id=str(session.id),
        token=token,
        livekit_url=settings.livekit_url,
        room_name=session.room_name,
        lecture_chapter_id=lecture_chapter_id,
    )


@router.get("/{session_id}", response_model=SessionInfo)
async def get_session(request: Request, session_id: UUID) -> SessionInfo:
    manager = _get_manager(request)
    try:
        return await manager.get_session(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found") from None


@router.post("/{session_id}/end", response_model=SessionInfo)
async def end_session(request: Request, session_id: UUID) -> SessionInfo:
    manager = _get_manager(request)
    try:
        return await manager.end_session(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found") from None
