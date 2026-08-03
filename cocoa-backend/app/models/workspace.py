"""Workspace, Membership, Passage — collaboration surface (PRD-v2)."""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class Workspace(BaseModel, Base):
    """Concrete workstream container inside a Namespace (空间)."""

    __tablename__ = "workspaces"
    __table_args__ = (
        Index(
            "uq_workspaces_namespace_slug",
            "namespace_id",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    namespace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("namespaces.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)

    def __repr__(self) -> str:
        cls = type(self).__name__
        return f"<{cls} {self.id!r} slug={self.slug!r}>"


class Membership(BaseModel, Base):
    """User XOR Instance seal in a Workspace with canvas position."""

    __tablename__ = "memberships"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL) <> (instance_id IS NOT NULL)",
            name="ck_memberships_exclusive_fk",
        ),
        Index(
            "uq_memberships_workspace_user",
            "workspace_id",
            "user_id",
            unique=True,
            postgresql_where=text(
                "deleted_at IS NULL AND user_id IS NOT NULL"
            ),
        ),
        Index(
            "uq_memberships_workspace_instance",
            "workspace_id",
            "instance_id",
            unique=True,
            postgresql_where=text(
                "deleted_at IS NULL AND instance_id IS NOT NULL"
            ),
        ),
        Index(
            "uq_memberships_workspace_pos",
            "workspace_id",
            "posx",
            "posy",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False
    )
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    instance_id: Mapped[str | None] = mapped_column(
        ForeignKey("instances.id"), nullable=True
    )
    posx: Mapped[int] = mapped_column(Integer, nullable=False)
    posy: Mapped[int] = mapped_column(Integer, nullable=False)
    # v4.0: static ``role`` column physically dropped (design §3.6 / §4.2).
    # Authorization is computed from Contract atoms, never from Membership.
    permissions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        cls = type(self).__name__
        return f"<{cls} {self.id!r} workspace={self.workspace_id!r}>"


class Passage(BaseModel, Base):
    """Duplex Membership↔Membership edge (default ``mode=dual``).

    ``from_membership_id`` / ``to_membership_id`` are a canonical undirected
    pair for ``mode=dual``: lexicographically smaller id is always stored in
    ``from_membership_id``. Click / request order does not matter.
    """

    __tablename__ = "passages"
    __table_args__ = (
        CheckConstraint(
            "from_membership_id IS NOT NULL AND to_membership_id IS NOT NULL",
            name="ck_passages_membership_endpoints",
        ),
        Index(
            "uq_passages_active_edge",
            "workspace_id",
            "from_membership_id",
            "to_membership_id",
            unique=True,
            postgresql_where=text(
                "is_active IS TRUE AND deleted_at IS NULL"
            ),
        ),
    )

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False
    )
    from_membership_id: Mapped[str] = mapped_column(
        ForeignKey("memberships.id"), nullable=False
    )
    to_membership_id: Mapped[str] = mapped_column(
        ForeignKey("memberships.id"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="dual", server_default="dual"
    )
    edge_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        cls = type(self).__name__
        return (
            f"<{cls} {self.id!r} workspace={self.workspace_id!r}"
            f" from={self.from_membership_id!r}"
            f" to={self.to_membership_id!r} mode={self.mode!r}>"
        )
