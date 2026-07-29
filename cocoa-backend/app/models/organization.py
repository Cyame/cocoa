"""Organization and Namespace — tenant hierarchy (PRD-v2).

Namespace is a **scenario** partition (e.g. coding / social-media), not env.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class Organization(BaseModel, Base):
    """Tenant boundary (世界). Single-tenant default slug=default."""

    __tablename__ = "organizations"
    __table_args__ = (
        Index(
            "uq_organizations_slug",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    def __repr__(self) -> str:
        cls = type(self).__name__
        return f"<{cls} {self.id!r} slug={self.slug!r}>"


class Namespace(BaseModel, Base):
    """Scenario partition (次元) within an Organization. Entity lives here."""

    __tablename__ = "namespaces"
    __table_args__ = (
        Index(
            "uq_namespaces_org_slug",
            "org_id",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        cls = type(self).__name__
        return f"<{cls} {self.id!r} slug={self.slug!r} org={self.org_id!r}>"
