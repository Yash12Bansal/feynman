"""Session management endpoints — create sessions and generate LiveKit tokens."""

from uuid import uuid4

import structlog
from fastapi import APIRouter
from livekit.api import AccessToken, VideoGrants
from pydantic import BaseModel

from feynman.config import settings

logger = structlog.get_logger()
router = APIRouter()


class CreateSessionResponse(BaseModel):
    session_id: str
    token: str
    livekit_url: str


@router.post("", response_model=CreateSessionResponse)
async def create_session() -> CreateSessionResponse:
    session_id = str(uuid4())
    room_name = f"feynman-{session_id}"

    token = (
        AccessToken(api_key=settings.livekit_api_key, api_secret=settings.livekit_api_secret)
        .with_identity(f"classroom-{session_id[:8]}")
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

    logger.info("session.created", session_id=session_id, room_name=room_name)

    return CreateSessionResponse(
        session_id=session_id,
        token=token,
        livekit_url=settings.livekit_url,
    )
