"""AiGene — unified deep-sea gene (PRD-v2: no kind enum)."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class AiGene(BaseModel, Base):
    """Named capability bundle. Manifest is unified; packaging via gene_refs[]."""

    __tablename__ = "ai_genes"
    __table_args__ = (
        Index(
            "uq_ai_genes_slug",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=list)
    manifest: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        cls = type(self).__name__
        return f"<{cls} {self.id!r} slug={self.slug!r}>"


class BaseClassAiGene(BaseModel, Base):
    """N:N junction BaseClass ↔ AiGene."""

    __tablename__ = "base_class_ai_genes"
    __table_args__ = (
        Index(
            "uq_base_class_ai_genes",
            "base_class_id",
            "ai_gene_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    base_class_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("base_classes.id"), nullable=False
    )
    ai_gene_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_genes.id"), nullable=False
    )
