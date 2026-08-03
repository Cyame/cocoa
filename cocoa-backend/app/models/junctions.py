"""Capability / AiGene junction tables (v4.0 — FK-only links).

The 3-layer market (Capability L1 / AiGene L2 / BaseClass L3) is wired with
explicit junction rows instead of embedded JSONB arrays:

- ``base_class_capabilities`` — BaseClass ↔ CapabilityMarketEntry
- ``entity_capabilities`` — Entity ↔ CapabilityMarketEntry (replaces the
  dropped ``entities.capabilities`` JSONB column as the write truth)
- ``entity_ai_genes`` — Entity ↔ AiGene

All junctions are soft-deletable with partial unique indexes so re-attach
after a soft delete does not collide.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class BaseClassCapability(BaseModel, Base):
    """N:N junction BaseClass ↔ CapabilityMarketEntry."""

    __tablename__ = "base_class_capabilities"
    __table_args__ = (
        Index(
            "uq_base_class_capabilities",
            "base_class_id",
            "capability_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    base_class_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("base_classes.id"), nullable=False
    )
    capability_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("capability_market.id"), nullable=False
    )


class EntityCapability(BaseModel, Base):
    """N:N junction Entity ↔ CapabilityMarketEntry."""

    __tablename__ = "entity_capabilities"
    __table_args__ = (
        Index(
            "uq_entity_capabilities",
            "entity_id",
            "capability_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entities.id"), nullable=False
    )
    capability_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("capability_market.id"), nullable=False
    )


class EntityAiGene(BaseModel, Base):
    """N:N junction Entity ↔ AiGene."""

    __tablename__ = "entity_ai_genes"
    __table_args__ = (
        Index(
            "uq_entity_ai_genes",
            "entity_id",
            "ai_gene_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entities.id"), nullable=False
    )
    ai_gene_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_genes.id"), nullable=False
    )
