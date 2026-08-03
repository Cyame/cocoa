"""user_genes — atomic human permissions (觉醒基因, v4.0 catalog-neutral)."""

from __future__ import annotations

import enum

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class UserGeneKind(str, enum.Enum):
    builtin = "builtin"
    custom = "custom"


class UserGeneEffectScope(str, enum.Enum):
    """Layer at which an atomic permission takes effect (design §3.6)."""

    platform = "platform"
    org = "org"
    namespace = "namespace"
    workspace = "workspace"


class UserGene(BaseModel, Base):
    """One atomic ``can_*`` permission. Catalog-neutral: describes the
    permission itself, never who holds it (grants live on Contracts)."""

    __tablename__ = "user_genes"
    __table_args__ = (
        Index(
            "uq_user_genes_slug",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint(
            "effect_scope IN ('platform', 'org', 'namespace', 'workspace')",
            name="ck_user_genes_effect_scope",
        ),
    )

    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(
        String(20), nullable=False, default=UserGeneKind.builtin.value
    )
    effect_scope: Mapped[str] = mapped_column(
        String(20), nullable=False, default=UserGeneEffectScope.org.value
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
