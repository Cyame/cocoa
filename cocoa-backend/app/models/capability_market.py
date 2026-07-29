"""CapabilityMarketEntry (L1) — atomic capability marketplace.

Per docs/prd-v1.md §13.6.10.2.1: a single capability (skill / tool / mcp /
lsp) is a globally addressable, named unit. CapabilityMarketEntry is the
canonical marketplace row that other layers (Entity / BaseClass / Gene)
reference. The 3-layer market is global, not workspace-scoped (v1
simplification).

Created via:
- A. 自动晋升 (promote) — when an Entity is promoted, new capabilities are
   written here with ``created_via="promote"`` and ``source_entity_slug``
   pointing at the originating Entity.
- B. 超管手动 (manual) — admins create rows directly with ``created_via="manual"``
   and ``source_entity_slug=None``.

Soft-delete with partial unique index on ``name`` (kebab-case slug) so
soft-deleted rows free up the slug for re-creation.
"""

from __future__ import annotations

from enum import Enum

from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class CapabilityType(str, Enum):
    """Atomic capability category. Stored as String, not PG native enum."""

    skill = "skill"
    tool = "tool"
    mcp = "mcp"
    lsp = "lsp"


class CapabilityCreatedVia(str, Enum):
    """How a CapabilityMarketEntry came into existence."""

    reap = "reap"        # reserved for future reaper flow (per PRD §13.6.2)
    promote = "promote"  # produced by an Entity promotion
    manual = "manual"    # admin hand-created


class CapabilityMarketEntry(BaseModel, Base):
    """A single atomic capability in the global marketplace.

    See ``docs/prd-v1.md`` §13.6.10.2.1 for the full schema. ``tags`` is a
    list of free-form strings used for filtering in the UI; ``config_template``
    is type-specific (e.g. MCP connection placeholders).
    """

    __tablename__ = "capability_market"
    __table_args__ = (
        Index(
            "uq_capability_market_name",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CapabilityType.skill.value
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_template: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True, default=list
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    created_via: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CapabilityCreatedVia.manual.value
    )
    source_entity_slug: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )

    def __repr__(self) -> str:
        cls = type(self).__name__
        return (
            f"<{cls} {self.id!r} name={self.name!r}"
            f" type={self.type!r} via={self.created_via!r}>"
        )
