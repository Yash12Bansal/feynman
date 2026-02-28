"""Teaching session lifecycle management.

Orchestrates session creation, state tracking, and teardown across Redis
(hot state for active teaching) and PostgreSQL (durable history).
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker

from feynman.agent.states import TeachingState
from feynman.common.exceptions import SessionNotFoundError
from feynman.common.types import Subject
from feynman.session.models import SessionModel
from feynman.session.schemas import SessionCreate, SessionInfo, SessionStatus
from feynman.session.store import SessionRedisStore, SessionRepository

logger = structlog.get_logger()


class SessionManager:
    """Orchestrates session lifecycle across Redis and PostgreSQL.

    Write path: create/activate/end write to both stores.
    Hot path: teaching state updates write only to Redis.
    Read path: Redis first (active sessions), Postgres fallback (ended sessions).
    """

    def __init__(self, db_factory: async_sessionmaker, redis: Redis) -> None:
        self._db_factory = db_factory
        self._redis = SessionRedisStore(redis)

    async def create_session(self, create: SessionCreate | None = None) -> SessionInfo:
        session_id = uuid4()
        room_name = f"feynman-{session_id}"
        subject = create.subject if create else None
        now = datetime.now(tz=UTC)

        async with self._db_factory() as db:
            repo = SessionRepository(db)
            model = SessionModel(
                id=session_id,
                room_name=room_name,
                subject=subject.value if subject else None,
                status=SessionStatus.PENDING,
                teaching_state=TeachingState.IDLE,
            )
            model = await repo.create(model)

        await self._redis.seed(
            session_id,
            status=SessionStatus.PENDING,
            teaching_state=TeachingState.IDLE,
            room_name=room_name,
            subject=subject.value if subject else None,
            created_at=model.created_at or now,
        )

        logger.info("session.created", session_id=str(session_id), room_name=room_name)
        return _model_to_info(model)

    async def get_session(self, session_id: UUID) -> SessionInfo:
        # Hot path: check Redis for active sessions
        hot = await self._redis.get(session_id)
        if hot:
            return _redis_to_info(session_id, hot)

        # Cold path: fall back to Postgres
        async with self._db_factory() as db:
            repo = SessionRepository(db)
            model = await repo.get_by_id(session_id)
            if not model:
                raise SessionNotFoundError(f"Session {session_id} not found")
            return _model_to_info(model)

    async def get_session_by_room(self, room_name: str) -> SessionInfo:
        async with self._db_factory() as db:
            repo = SessionRepository(db)
            model = await repo.get_by_room_name(room_name)
            if not model:
                raise SessionNotFoundError(f"Session for room {room_name} not found")
            return _model_to_info(model)

    async def activate_session(self, session_id: UUID) -> SessionInfo:
        """Mark session as active when teaching begins."""
        async with self._db_factory() as db:
            repo = SessionRepository(db)
            model = await repo.get_by_id(session_id)
            if not model:
                raise SessionNotFoundError(f"Session {session_id} not found")
            model.status = SessionStatus.ACTIVE
            model.teaching_state = TeachingState.GREETING
            model = await repo.update(model)

        await self._redis.update_status(
            session_id,
            status=SessionStatus.ACTIVE,
            teaching_state=TeachingState.GREETING,
        )

        logger.info("session.activated", session_id=str(session_id))
        return _model_to_info(model)

    async def update_teaching_state(
        self,
        session_id: UUID,
        *,
        state: TeachingState,
        branch_depth: int = 1,
    ) -> None:
        """Update teaching state during active session. Hot path — Redis only."""
        await self._redis.update_teaching_state(
            session_id,
            teaching_state=state,
            branch_depth=branch_depth,
        )

    async def end_session(self, session_id: UUID) -> SessionInfo:
        """End the session. Syncs final state to Postgres and cleans Redis."""
        now = datetime.now(tz=UTC)

        # Capture final teaching state from Redis before cleanup
        hot = await self._redis.get(session_id)
        final_state = TeachingState(hot["teaching_state"]) if hot else TeachingState.ENDING

        async with self._db_factory() as db:
            repo = SessionRepository(db)
            model = await repo.get_by_id(session_id)
            if not model:
                raise SessionNotFoundError(f"Session {session_id} not found")
            model.status = SessionStatus.ENDED
            model.teaching_state = final_state
            model.ended_at = now
            model = await repo.update(model)

        await self._redis.delete(session_id)

        logger.info("session.ended", session_id=str(session_id))
        return _model_to_info(model)


def _model_to_info(model: SessionModel, branch_depth: int = 1) -> SessionInfo:
    """Convert SQLAlchemy model to SessionInfo."""
    return SessionInfo(
        id=model.id,
        room_name=model.room_name,
        subject=Subject(model.subject) if model.subject else None,
        status=SessionStatus(model.status),
        teaching_state=TeachingState(model.teaching_state),
        branch_depth=branch_depth,
        created_at=model.created_at,
        updated_at=model.updated_at,
        ended_at=model.ended_at,
    )


def _redis_to_info(session_id: UUID, data: dict[str, str]) -> SessionInfo:
    """Convert Redis hash data to SessionInfo."""
    return SessionInfo(
        id=session_id,
        room_name=data["room_name"],
        subject=Subject(data["subject"]) if data.get("subject") else None,
        status=SessionStatus(data["status"]),
        teaching_state=TeachingState(data["teaching_state"]),
        branch_depth=int(data.get("branch_depth", "1")),
        created_at=datetime.fromisoformat(data["created_at"]),
        updated_at=datetime.fromisoformat(data["updated_at"]),
        ended_at=None,
    )
