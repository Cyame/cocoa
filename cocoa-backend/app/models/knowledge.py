"""knowledge_entries / knowledge_dimensions — scoped knowledge rows (v4.2).

Knowledge rows are scoped ``system | org | namespace | workspace`` with
nullable ownership ids. Uniqueness follows the H3 COALESCE-sentinel design:
an active ``key`` (or dimension ``slug``) must be unique per ``(scope,
organization_id, namespace_id, workspace_id)`` where NULL ownership ids are
mapped to ``SCOPE_NULL_SENTINEL`` so that e.g. two ``system`` rows with the
same key collide (PG treats NULL != NULL otherwise).

Write-time lowercase normalization of ``key`` happens in the API layer, NOT
here — the model stores whatever it is given.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel

SCOPE_NULL_SENTINEL = "00000000-0000-0000-0000-000000000000"

_SCOPE_COALESCE = "COALESCE({column}, '{sentinel}')"
_SCOPE_CHECK = "scope IN ('system', 'org', 'namespace', 'workspace')"


class KnowledgeEntry(BaseModel, Base):
    """One scoped knowledge item injected into instance scaffolds."""

    __tablename__ = "knowledge_entries"
    __table_args__ = (
        Index(
            "uq_knowledge_entries_active_key",
            "scope",
            text(
                _SCOPE_COALESCE.format(
                    column="organization_id", sentinel=SCOPE_NULL_SENTINEL
                )
            ),
            text(
                _SCOPE_COALESCE.format(
                    column="namespace_id", sentinel=SCOPE_NULL_SENTINEL
                )
            ),
            text(
                _SCOPE_COALESCE.format(
                    column="workspace_id", sentinel=SCOPE_NULL_SENTINEL
                )
            ),
            text(
                _SCOPE_COALESCE.format(
                    column="dimension_id", sentinel=SCOPE_NULL_SENTINEL
                )
            ),
            "key",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_knowledge_entries_scope_org",
            "scope",
            "organization_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_knowledge_entries_workspace_key",
            "workspace_id",
            "key",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_knowledge_entries_entity_id",
            "entity_id",
            postgresql_where=text("entity_id IS NOT NULL"),
        ),
        CheckConstraint(_SCOPE_CHECK, name="ck_knowledge_entries_scope"),
    )

    key: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    dimension_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("knowledge_dimensions.id"), nullable=True
    )
    scope: Mapped[str] = mapped_column(
        String(20), nullable=False, default="org", server_default="org"
    )
    organization_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=True
    )
    namespace_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("namespaces.id"), nullable=True
    )
    workspace_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workspaces.id"), nullable=True
    )
    entity_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("entities.id"), nullable=True
    )
    instance_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("instances.id"), nullable=True
    )

    def __repr__(self) -> str:
        cls = type(self).__name__
        return f"<{cls} {self.id!r} key={self.key!r} scope={self.scope!r}>"


class KnowledgeDimension(BaseModel, Base):
    """A knowledge classification bucket (name / slug / description)."""

    __tablename__ = "knowledge_dimensions"
    __table_args__ = (
        Index(
            "uq_knowledge_dimensions_active_slug",
            "scope",
            text(
                _SCOPE_COALESCE.format(
                    column="organization_id", sentinel=SCOPE_NULL_SENTINEL
                )
            ),
            text(
                _SCOPE_COALESCE.format(
                    column="namespace_id", sentinel=SCOPE_NULL_SENTINEL
                )
            ),
            text(
                _SCOPE_COALESCE.format(
                    column="workspace_id", sentinel=SCOPE_NULL_SENTINEL
                )
            ),
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_knowledge_dimensions_scope_org",
            "scope",
            "organization_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint(_SCOPE_CHECK, name="ck_knowledge_dimensions_scope"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(255), nullable=False, default=lambda: str(uuid.uuid4())
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope: Mapped[str] = mapped_column(
        String(20), nullable=False, default="org", server_default="org"
    )
    organization_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=True
    )
    namespace_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("namespaces.id"), nullable=True
    )
    workspace_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workspaces.id"), nullable=True
    )

    def __repr__(self) -> str:
        cls = type(self).__name__
        return f"<{cls} {self.id!r} slug={self.slug!r} scope={self.scope!r}>"
