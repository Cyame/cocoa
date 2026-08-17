"""DeployRecord model — per-Instance deploy pipeline run history.

Each row tracks one deploy/rebuild/restore attempt for a given Instance.
``uq_deploy_records_instance_revision`` partial unique index enforces
monotonic revision numbering on active records; soft-deleted rows are
excluded so the same revision slot can be reclaimed after a rollback.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class DeployAction(str, Enum):
    """Kind of deploy operation being recorded."""

    deploy = "deploy"
    rebuild = "rebuild"
    restore = "restore"


class DeployStatus(str, Enum):
    """Lifecycle status of a deploy record."""

    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"
    cancelled = "cancelled"


class DeployRecord(BaseModel, Base):
    """One deploy pipeline run for an Instance.

    Revision increments per ``instance_id`` on each new active record;
    soft-deleted rows are excluded via the partial unique index, so a
    rollback can reuse the same revision slot for the next attempt.
    """

    __tablename__ = "deploy_records"
    __table_args__ = (
        Index(
            "uq_deploy_records_instance_revision",
            "instance_id",
            "revision",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    instance_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("instances.id"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    action: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DeployAction.deploy.value
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DeployStatus.pending.value
    )
    image_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    config_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    triggered_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        cls = type(self).__name__
        return (
            f"<{cls} {self.id!r} instance={self.instance_id!r}"
            f" action={self.action!r} status={self.status!r}"
            f" revision={self.revision}>"
        )
