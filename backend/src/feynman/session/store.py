"""Session persistence — Redis for hot state, PostgreSQL for history."""

from datetime import UTC, datetime
from uuid import UUID

import structlog
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from feynman.agent.states import TeachingState
from feynman.session.models import SessionModel
from feynman.session.schemas import SessionStatus

logger = structlog.get_logger()

_KEY_PREFIX = "session"
_TTL_SECONDS = 86400  # 24 hours


def _key(session_id: UUID) -> str:
    return f"{_KEY_PREFIX}:{session_id}"


class SessionRedisStore:
    """Hot session state in Redis for fast reads during active teaching.

    Stores the subset of session data that changes frequently (teaching state,
    branch depth) plus enough context to serve reads without hitting Postgres.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def seed(
        self,
        session_id: UUID,
        *,
        status: SessionStatus,
        teaching_state: TeachingState,
        room_name: str,
        subject: str | None = None,
        created_at: datetime,
    ) -> None:
        """Seed initial session state. Called once on session creation."""
        now = datetime.now(tz=UTC).isoformat()
        key = _key(session_id)
        await self._redis.hset(
            key,
            mapping={
                "status": str(status),
                "teaching_state": str(teaching_state),
                "branch_depth": "1",
                "room_name": room_name,
                "subject": subject or "",
                "created_at": created_at.isoformat(),
                "updated_at": now,
            },
        )
        await self._redis.expire(key, _TTL_SECONDS)

    async def get(self, session_id: UUID) -> dict[str, str] | None:
        """Get full hot state. Returns None if session not in Redis."""
        data = await self._redis.hgetall(_key(session_id))
        return data if data else None

    async def update_status(
        self,
        session_id: UUID,
        *,
        status: SessionStatus,
        teaching_state: TeachingState,
    ) -> None:
        """Update lifecycle status (e.g., pending → active, active → ended)."""
        now = datetime.now(tz=UTC).isoformat()
        await self._redis.hset(
            _key(session_id),
            mapping={
                "status": str(status),
                "teaching_state": str(teaching_state),
                "updated_at": now,
            },
        )

    async def update_teaching_state(
        self,
        session_id: UUID,
        *,
        teaching_state: TeachingState,
        branch_depth: int,
    ) -> None:
        """Update teaching state during active session. Called frequently."""
        now = datetime.now(tz=UTC).isoformat()
        await self._redis.hset(
            _key(session_id),
            mapping={
                "teaching_state": str(teaching_state),
                "branch_depth": str(branch_depth),
                "updated_at": now,
            },
        )

    async def delete(self, session_id: UUID) -> None:
        """Remove session from Redis (on session end)."""
        await self._redis.delete(_key(session_id))


class SessionRepository:
    """Durable session records in PostgreSQL."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, model: SessionModel) -> SessionModel:
        self._db.add(model)
        await self._db.commit()
        await self._db.refresh(model)
        return model

    async def get_by_id(self, session_id: UUID) -> SessionModel | None:
        result = await self._db.execute(select(SessionModel).where(SessionModel.id == session_id))
        return result.scalar_one_or_none()

    async def get_by_room_name(self, room_name: str) -> SessionModel | None:
        result = await self._db.execute(
            select(SessionModel).where(SessionModel.room_name == room_name)
        )
        return result.scalar_one_or_none()

    async def update(self, model: SessionModel) -> SessionModel:
        await self._db.commit()
        await self._db.refresh(model)
        return model
