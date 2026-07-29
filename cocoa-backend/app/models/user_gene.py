"""user_genes — human permission packs (觉醒基因)."""

from __future__ import annotations

import enum

from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class UserGeneKind(str, enum.Enum):
    builtin = "builtin"
    custom = "custom"


class UserGene(BaseModel, Base):
    """Named pack of can_* permission keys."""

    __tablename__ = "user_genes"
    __table_args__ = (
        Index(
            "uq_user_genes_slug",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(
        String(20), nullable=False, default=UserGeneKind.builtin.value
    )
    permission_keys: Mapped[list | None] = mapped_column(
        JSONB, nullable=False, default=list
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        cls = type(self).__name__
        return f"<{cls} {self.id!r} slug={self.slug!r}>"


class UserUserGene(BaseModel, Base):
    """N:N junction User ↔ UserGene."""

    __tablename__ = "user_user_genes"
    __table_args__ = (
        Index(
            "uq_user_user_genes",
            "user_id",
            "user_gene_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    user_gene_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user_genes.id"), nullable=False
    )
