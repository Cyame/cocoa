"""Composer chat transcript — server-side messages for Workspace Composer.

Lifecycle: soft-deleted with the owning Namespace (same product lifetime as
the user's chat entry into that 次元). Scoped by workspace_id for IDE load.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class ComposerMessage(BaseModel, Base):
    """One bubble in the Workspace Composer transcript."""

    __tablename__ = "composer_messages"
    __table_args__ = (
        Index(
            "ix_composer_messages_workspace_created",
            "workspace_id",
            "created_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_composer_messages_namespace",
            "namespace_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    namespace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("namespaces.id"), nullable=False
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user|assistant|system
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    target_entity: Mapped[str | None] = mapped_column(String(255), nullable=True)
    instance_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("instances.id"), nullable=True
    )
    turn_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="completed"
    )  # responding|completed|failed
    author_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )

    def __repr__(self) -> str:
        cls = type(self).__name__
        return f"<{cls} {self.id!r} role={self.role!r} ws={self.workspace_id!r}>"
