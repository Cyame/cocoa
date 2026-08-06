"""Entity — per-Namespace AI identity (眷族) with BaseClass soft-ref (PRD-v2)."""

from __future__ import annotations

import enum

from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class EntityRank(str, enum.Enum):
    """AI Lab Rank — frozen at Entity create. Humans are director (not stored here)."""

    intern = "intern"
    researcher = "researcher"


class Entity(BaseModel, Base):
    """Scenario-scoped AI identity. Spawns Instances in Workspaces of the same Namespace."""

    __tablename__ = "entities"
    __table_args__ = (
        Index(
            "uq_entities_namespace_slug",
            "namespace_id",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # v4.0 D7: at most one cerebellum Entity per Namespace.
        Index(
            "uq_entities_cerebellum_per_ns",
            "namespace_id",
            unique=True,
            postgresql_where=text("is_cerebellum IS TRUE AND deleted_at IS NULL"),
        ),
    )

    namespace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("namespaces.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    preset_slug: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    rank: Mapped[str] = mapped_column(
        String(20), nullable=False, default=EntityRank.intern.value
    )
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_override: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # v4.9.3 knowledge dual-dimension: has knowledge slugs (real DB assets).
    has_knowledge: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    migration_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=None
    )
    # v4.0 D7: cerebellum flag (小脑). Capabilities moved to the
    # ``entity_capabilities`` junction (see app.models.junctions).
    is_cerebellum: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default="false"
    )

    def __repr__(self) -> str:
        cls = type(self).__name__
        return f"<{cls} {self.id!r} slug={self.slug!r} rank={self.rank!r}>"
