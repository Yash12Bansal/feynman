"""Tests for the session lifecycle manager."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from feynman.agent.states import TeachingState
from feynman.common.exceptions import SessionNotFoundError
from feynman.session.manager import SessionManager
from feynman.session.models import SessionModel
from feynman.session.schemas import SessionCreate, SessionStatus


def _make_model(
    *,
    session_id=None,
    room_name="feynman-test",
    status=SessionStatus.PENDING,
    teaching_state=TeachingState.IDLE,
    subject=None,
) -> SessionModel:
    """Create a SessionModel with timestamps filled in."""
    model = SessionModel(
        id=session_id or uuid4(),
        room_name=room_name,
        status=status,
        teaching_state=teaching_state,
        subject=subject,
    )
    now = datetime.now(tz=UTC)
    model.created_at = now
    model.updated_at = now
    model.ended_at = None
    return model


@pytest.fixture
def mock_db_factory():
    """Mock async_sessionmaker that yields a mock AsyncSession."""
    db = AsyncMock()
    factory = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=None)
    factory.return_value = ctx
    return factory, db


@pytest.fixture
def mock_redis():
    return AsyncMock()


@pytest.fixture
def manager(mock_db_factory, mock_redis):
    factory, _ = mock_db_factory
    return SessionManager(factory, mock_redis)


async def test_create_session(manager: SessionManager, mock_db_factory, mock_redis):
    _, db = mock_db_factory

    # Mock the repository's create: capture what's added and return it
    async def fake_commit():
        pass

    async def fake_refresh(obj):
        obj.created_at = obj.created_at or datetime.now(tz=UTC)
        obj.updated_at = obj.updated_at or datetime.now(tz=UTC)

    db.commit = AsyncMock(side_effect=fake_commit)
    db.refresh = AsyncMock(side_effect=fake_refresh)

    session = await manager.create_session()

    assert session.status == SessionStatus.PENDING
    assert session.teaching_state == TeachingState.IDLE
    assert session.room_name.startswith("feynman-")
    assert session.subject is None
    assert session.ended_at is None

    # Verify Redis was seeded
    mock_redis.hset.assert_called_once()
    mock_redis.expire.assert_called_once()


async def test_create_session_with_subject(manager: SessionManager, mock_db_factory, mock_redis):
    _, db = mock_db_factory

    async def fake_refresh(obj):
        obj.created_at = obj.created_at or datetime.now(tz=UTC)
        obj.updated_at = obj.updated_at or datetime.now(tz=UTC)

    db.commit = AsyncMock()
    db.refresh = AsyncMock(side_effect=fake_refresh)

    from feynman.common.types import Subject

    session = await manager.create_session(SessionCreate(subject=Subject.MATH))

    assert session.subject == Subject.MATH


async def test_get_session_from_redis(manager: SessionManager, mock_redis):
    session_id = uuid4()
    now = datetime.now(tz=UTC).isoformat()
    mock_redis.hgetall = AsyncMock(
        return_value={
            "status": "active",
            "teaching_state": "teaching",
            "branch_depth": "2",
            "room_name": f"feynman-{session_id}",
            "subject": "math",
            "created_at": now,
            "updated_at": now,
        }
    )

    session = await manager.get_session(session_id)

    assert session.id == session_id
    assert session.status == SessionStatus.ACTIVE
    assert session.teaching_state == TeachingState.TEACHING
    assert session.branch_depth == 2


async def test_get_session_falls_back_to_postgres(
    manager: SessionManager, mock_db_factory, mock_redis
):
    _, db = mock_db_factory
    session_id = uuid4()

    # Redis returns empty (session not in hot state)
    mock_redis.hgetall = AsyncMock(return_value={})

    model = _make_model(session_id=session_id, status=SessionStatus.ENDED)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = model
    db.execute = AsyncMock(return_value=result_mock)

    session = await manager.get_session(session_id)

    assert session.id == session_id
    assert session.status == SessionStatus.ENDED


async def test_get_session_not_found(manager: SessionManager, mock_db_factory, mock_redis):
    _, db = mock_db_factory

    mock_redis.hgetall = AsyncMock(return_value={})

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result_mock)

    with pytest.raises(SessionNotFoundError):
        await manager.get_session(uuid4())


async def test_activate_session(manager: SessionManager, mock_db_factory, mock_redis):
    _, db = mock_db_factory
    session_id = uuid4()

    model = _make_model(session_id=session_id)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = model
    db.execute = AsyncMock(return_value=result_mock)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    session = await manager.activate_session(session_id)

    assert session.status == SessionStatus.ACTIVE
    assert session.teaching_state == TeachingState.GREETING
    # Redis status was updated
    mock_redis.hset.assert_called()


async def test_end_session(manager: SessionManager, mock_db_factory, mock_redis):
    _, db = mock_db_factory
    session_id = uuid4()

    # Redis has the final teaching state
    now = datetime.now(tz=UTC).isoformat()
    mock_redis.hgetall = AsyncMock(
        return_value={
            "status": "active",
            "teaching_state": "summarizing",
            "branch_depth": "1",
            "room_name": f"feynman-{session_id}",
            "subject": "",
            "created_at": now,
            "updated_at": now,
        }
    )

    model = _make_model(session_id=session_id, status=SessionStatus.ACTIVE)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = model
    db.execute = AsyncMock(return_value=result_mock)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    session = await manager.end_session(session_id)

    assert session.status == SessionStatus.ENDED
    assert session.teaching_state == TeachingState.SUMMARIZING
    assert session.ended_at is not None
    # Redis was cleaned up
    mock_redis.delete.assert_called_once()


async def test_update_teaching_state(manager: SessionManager, mock_redis):
    session_id = uuid4()

    await manager.update_teaching_state(
        session_id,
        state=TeachingState.HANDLING_DOUBT,
        branch_depth=3,
    )

    mock_redis.hset.assert_called_once()
    call_kwargs = mock_redis.hset.call_args
    mapping = call_kwargs.kwargs.get("mapping") or call_kwargs[1].get("mapping")
    assert mapping["teaching_state"] == "handling_doubt"
    assert mapping["branch_depth"] == "3"
