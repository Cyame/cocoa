"""Corridor CRUD schemas.

These DTOs are decoupled from the ORM model — they define what the API
accepts and returns, while the model (``app.models.office.Corridor``)
owns the DB schema.

Corridors are **polymorphic** (P9 Todo 8): each side of the edge is
either a :class:`Membership` (the P5 contract) or a
:class:`CorridorNode` (a first-class canvas anchor introduced in P9).
The model-level CHECK constraints reject any payload where both
``from_*`` columns on a side are set or both are null; the Pydantic
validator here provides a friendlier 422 instead of a 500 if the
client violates that contract.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator


class CorridorCreate(BaseModel):
    """Payload for ``POST /api/v1/messaging/corridors``.

    Exactly one of ``from_membership_id`` / ``from_corridor_node_id``
    must be provided; likewise on the *to* side. All four may NOT be
    set simultaneously.
    """

    office_id: str
    from_membership_id: str | None = None
    to_membership_id: str | None = None
    from_corridor_node_id: str | None = None
    to_corridor_node_id: str | None = None

    @model_validator(mode="after")
    def _check_polymorphic(self) -> "CorridorCreate":
        from_count = sum(
            v is not None
            for v in (self.from_membership_id, self.from_corridor_node_id)
        )
        to_count = sum(
            v is not None
            for v in (self.to_membership_id, self.to_corridor_node_id)
        )
        if from_count != 1:
            raise ValueError(
                "Exactly one of from_membership_id or from_corridor_node_id"
                " must be set"
            )
        if to_count != 1:
            raise ValueError(
                "Exactly one of to_membership_id or to_corridor_node_id"
                " must be set"
            )
        return self


class CorridorUpdate(BaseModel):
    """Payload for ``PATCH /api/v1/messaging/corridors/{corridor_id}``.

    All fields are optional — only provided fields are updated.
    """

    is_active: bool | None = None
    edge_meta: dict | None = None


class CorridorOut(BaseModel):
    """Response body for a single Corridor."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    office_id: str
    from_membership_id: str | None
    to_membership_id: str | None
    from_corridor_node_id: str | None
    to_corridor_node_id: str | None
    is_active: bool
    edge_meta: dict | None
    created_at: datetime
    updated_at: datetime
