"""NamespaceContract — 契印 (Namespace ↔ User). PRD-v3.4."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class NamespaceContract(BaseModel, Base):
    """Human seal in a Namespace. Product name: 契印 (only at namespace layer)."""

    __tablename__ = "namespace_contracts"
    __table_args__ = (
        Index(
            "uq_namespace_contracts_ns_user",
            "namespace_id",
            "user_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    namespace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("namespaces.id"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="viewer")
    permissions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        cls = type(self).__name__
        return f"<{cls} {self.id!r} ns={self.namespace_id!r} user={self.user_id!r}>"
