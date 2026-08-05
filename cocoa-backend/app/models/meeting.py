"""Meeting + MeetingParticipant (v4.8).

Soft-delete everywhere (BaseModel). Both unique constraints are partial on
``deleted_at IS NULL`` per AGENTS.md — never a bare ``UniqueConstraint``.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class MeetingStatus(str, Enum):
    scheduled = "scheduled"
    active = "active"
    ended = "ended"
    cancelled = "cancelled"


class Meeting(BaseModel, Base):
    """A scheduled collaboration event in a Workspace."""

    __tablename__ = "meetings"

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    agenda: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=MeetingStatus.scheduled.value
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )

    def __repr__(self) -> str:
        cls = type(self).__name__
        return f"<{cls} {self.id!r} workspace={self.workspace_id!r} status={self.status!r}>"


class MeetingParticipant(BaseModel, Base):
    """A Membership seat invited to a Meeting."""

    __tablename__ = "meeting_participants"
    __table_args__ = (
        Index(
            "uq_meeting_participants_meeting_membership",
            "meeting_id",
            "membership_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "uq_meeting_participants_meeting_role",
            "meeting_id",
            "role_in_meeting",
            unique=True,
            postgresql_where=text(
                "deleted_at IS NULL AND role_in_meeting IS NOT NULL"
            ),
        ),
    )

    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id"), nullable=False
    )
    membership_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("memberships.id"), nullable=False
    )
    # Free-form role label inside the meeting (NOT the auth permission role).
    role_in_meeting: Mapped[str | None] = mapped_column(String(100), nullable=True)

    def __repr__(self) -> str:
        cls = type(self).__name__
        return f"<{cls} {self.id!r} meeting={self.meeting_id!r} membership={self.membership_id!r}>"
