"""SQLAlchemy models for teaching sessions."""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from feynman.agent.states import TeachingState
from feynman.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from feynman.session.schemas import SessionStatus


class SessionModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "sessions"

    room_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    subject: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=SessionStatus.PENDING)
    teaching_state: Mapped[str] = mapped_column(String(30), default=TeachingState.IDLE)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
