"""Office model — collaboration space with memberships and corridors."""

import enum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class MembershipRole(str, enum.Enum):
    """Roles a member can hold within an office."""

    owner = "owner"
    editor = "editor"
    viewer = "viewer"


class Office(BaseModel, Base):
    """A collaboration workspace that groups users and instances."""

    __tablename__ = "offices"
    __table_args__ = (
        Index(
            "uq_offices_slug",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    blackboard_ref: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        cls = type(self).__name__
        return f"<{cls} {self.id!r} slug={self.slug!r}>"


class Membership(BaseModel, Base):
    """Links a user or instance to an office with a role and canvas position.

    The ``posx`` / ``posy`` columns are free Cartesian coordinates on the
    office's 2D canvas (P9 — previously named ``hex_q`` / ``hex_r`` to
    imply axial hex-grid coordinates, but the canvas is now free
    Cartesian, not hex). A partial unique index on
    ``(office_id, posx, posy)`` (``uq_memberships_office_pos``) prevents
    two active memberships from sharing the same canvas cell.

    Has an exclusive-FK constraint: exactly one of ``user_id`` or
    ``instance_id`` must be non-null.
    """

    __tablename__ = "memberships"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL) <> (instance_id IS NOT NULL)",
            name="ck_memberships_exclusive_fk",
        ),
        Index(
            "uq_memberships_office_user",
            "office_id",
            "user_id",
            unique=True,
            postgresql_where=text(
                "deleted_at IS NULL AND user_id IS NOT NULL"
            ),
        ),
        Index(
            "uq_memberships_office_instance",
            "office_id",
            "instance_id",
            unique=True,
            postgresql_where=text(
                "deleted_at IS NULL AND instance_id IS NOT NULL"
            ),
        ),
        Index(
            "uq_memberships_office_pos",
            "office_id",
            "posx",
            "posy",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    office_id: Mapped[str] = mapped_column(
        ForeignKey("offices.id"), nullable=False
    )
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    instance_id: Mapped[str | None] = mapped_column(
        ForeignKey("instances.id"), nullable=True
    )
    posx: Mapped[int] = mapped_column(Integer, nullable=False)
    posy: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    permissions: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        cls = type(self).__name__
        return (
            f"<{cls} {self.id!r} office={self.office_id!r}"
            f" role={self.role!r}>"
        )


class Corridor(BaseModel, Base):
    """A directed edge between two memberships in the same office.

    Forms the adjacency graph for hex-grid navigation. Acyclicity is
    enforced at the service layer (P5), not via DB constraints.
    """

    __tablename__ = "corridors"
    __table_args__ = (
        Index(
            "uq_corridors_active_edge",
            "office_id",
            "from_membership_id",
            "to_membership_id",
            unique=True,
            postgresql_where=text(
                "is_active IS TRUE AND deleted_at IS NULL"
            ),
        ),
    )

    office_id: Mapped[str] = mapped_column(
        ForeignKey("offices.id"), nullable=False
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
    edge_meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        cls = type(self).__name__
        return (
            f"<{cls} {self.id!r} office={self.office_id!r}"
            f" from={self.from_membership_id!r} to={self.to_membership_id!r}>"
        )
