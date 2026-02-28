"""Session management endpoints — create sessions and generate LiveKit tokens."""

from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException, Request
from livekit.api import AccessToken, VideoGrants

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
                can_publish_data=False,
            )
        )
        .to_jwt()
    )


@router.post("", response_model=CreateSessionResponse)
async def create_session(
    request: Request,
    body: SessionCreate | None = None,
) -> CreateSessionResponse:
    manager = _get_manager(request)
    session = await manager.create_session(body)

    token = _create_livekit_token(
        room_name=session.room_name,
        identity=f"classroom-{session.id!s:.8}",
    )

    return CreateSessionResponse(
        session_id=str(session.id),
        token=token,
        livekit_url=settings.livekit_url,
        room_name=session.room_name,
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
