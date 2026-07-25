"""Event audit model — immutable audit trail of system actions.

Events are never deleted; ``deleted_at`` is always ``NULL``.
"""

from sqlalchemy import Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class Event(BaseModel, Base):
    """An immutable audit event recording a system action.

    Events are write-once, never updated, never deleted.
    """

    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_type_created", "type", "created_at"),
        Index("ix_events_resource", "resource_type", "resource_id"),
        Index("ix_events_request_id", "request_id"),
    )

    type: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    def __repr__(self) -> str:
        cls = type(self).__name__
        return f"<{cls} {self.id!r} type={self.type!r}>"
