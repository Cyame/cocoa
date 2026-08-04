"""Inject queue — durable downlink queue from Harness/Workspace to an Instance.

v4.7 H6 (`.omo/plans/v4-7-harness-collab.md`): soft-inject / wake / notify
deliveries are persisted here and polled by the instance's agent runtime.
Rows are allowed to repeat (no unique constraints) and are soft-deleted
after they age out of the completed states.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class InjectStatus(str, Enum):
    pending = "pending"
    delivered = "delivered"
    acked = "acked"
    failed = "failed"
    expired = "expired"


class InstanceInjectQueue(BaseModel, Base):
    """One inject delivery targeted at one instance.

    Lifecycle: ``pending`` → ``delivered`` (polled) → ``acked`` (host
    confirmed), or ``pending`` → ``failed`` / ``expired``. Soft-delete is
    used for cleanup — never a physical delete.
    """

    __tablename__ = "instance_inject_queue"
    __table_args__ = (
        Index("ix_instance_inject_queue_instance_status", "instance_id", "status"),
    )

    instance_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("instances.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # collab_inject | gene_inject | capability_inject | cerebellum_route
    delivery_mode: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # notify | soft_inject | wake
    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=InjectStatus.pending.value
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc) + timedelta(hours=1),
    )
    acked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    error_message: Mapped[str | None] = mapped_column(
        String(2000), nullable=True, default=None
    )

    def __repr__(self) -> str:
        cls = type(self).__name__
        return (
            f"<{cls} {self.id!r} instance={self.instance_id!r}"
            f" kind={self.kind!r} status={self.status!r}>"
        )
