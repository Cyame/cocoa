"""CorridorNode model — first-class canvas element distinct from Membership.

A CorridorNode is a typed "passage point" on the topology canvas: a named,
positioned element that corridors can attach to. It is **not** a member of
the office (no role, no user/instance FK); it is a structural node, like
nodeskclaw's ``CorridorHex``. This gives the P9 topology viz a way to
visually anchor a group of corridors at a single coordinate (e.g. a
shared inbox, a topic hub, an integration boundary) without inventing a
synthetic membership for it.

Three connection kinds are supported (P9 Todo 8 — Corridor polymorphic):

- M <-> M (membership to membership; original P5)
- M <-> CN (membership to corridor node; new)
- CN <-> CN (corridor node to corridor node; new)

A partial unique index ``uq_corridor_nodes_office_pos`` keeps
(office_id, posx, posy) unique among active rows so two CorridorNodes
cannot share a canvas cell, mirroring the
``uq_memberships_office_pos`` contract on Membership.
"""

import enum

from sqlalchemy import ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class CorridorNodeStatus(str, enum.Enum):
    """Lifecycle states for a corridor node.

    Mirrors a simplified subset of the membership workflow: a node is
    created ``active`` and can be ``paused`` (still rendered, but
    corridors through it do not animate) or ``archived`` (hidden from
    the topology by default, retained for history).
    """

    active = "active"
    paused = "paused"
    archived = "archived"


class CorridorNode(BaseModel, Base):
    """A named, positioned canvas element that corridors can attach to.

    Distinct from :class:`Membership` in that it does not represent a
    principal in the office — it is a structural anchor for corridors
    only. Has its own ``display_name`` and an optional ``glow_color``
    override (the rest of the glow comes from the office topology state
    like any other node).
    """

    __tablename__ = "corridor_nodes"
    __table_args__ = (
        Index(
            "uq_corridor_nodes_office_pos",
            "office_id",
            "posx",
            "posy",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    office_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("offices.id"), nullable=False
    )
    posx: Mapped[int] = mapped_column(Integer, nullable=False)
    posy: Mapped[int] = mapped_column(Integer, nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    glow_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=CorridorNodeStatus.active.value
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )

    def __repr__(self) -> str:
        cls = type(self).__name__
        return (
            f"<{cls} {self.id!r} office={self.office_id!r}"
            f" pos=({self.posx!r},{self.posy!r})"
            f" name={self.display_name!r}>"
        )
