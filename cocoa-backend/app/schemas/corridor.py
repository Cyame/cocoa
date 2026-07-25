"""Corridor CRUD schemas.

These DTOs are decoupled from the ORM model — they define what the API
accepts and returns, while the model (``app.models.office.Corridor``)
owns the DB schema.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CorridorCreate(BaseModel):
    """Payload for ``POST /api/v1/messaging/corridors``."""

    office_id: str
    from_membership_id: str
    to_membership_id: str


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
    from_membership_id: str
    to_membership_id: str
    is_active: bool
    edge_meta: dict | None
    created_at: datetime
    updated_at: datetime
