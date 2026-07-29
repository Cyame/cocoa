"""Instance — Workspace-scoped materialization of an Entity."""

from enum import Enum

from sqlalchemy import JSON, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class InstanceStatus(str, Enum):
    creating = "creating"
    pending = "pending"
    deploying = "deploying"
    running = "running"
    restarting = "restarting"
    failed = "failed"
    deleting = "deleting"


class Instance(BaseModel, Base):
    """Running pod materialization of an Entity in one Workspace."""

    __tablename__ = "instances"
    __table_args__ = (
        Index(
            "uq_instances_workspace_path",
            "workspace_path",
            unique=True,
            postgresql_where=text(
                "deleted_at IS NULL AND workspace_path IS NOT NULL"
            ),
        ),
    )

    entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entities.id"), nullable=False
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), nullable=False
    )
    workspace_path: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=InstanceStatus.creating.value
    )
    runtime_config: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    proxy_token: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None
    )
    active_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=None
    )

    def __repr__(self) -> str:
        cls = type(self).__name__
        return (
            f"<{cls} {self.id!r} entity={self.entity_id!r}"
            f" workspace={self.workspace_id!r} status={self.status!r}>"
        )
