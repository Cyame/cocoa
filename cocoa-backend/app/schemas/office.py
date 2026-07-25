"""Request/response schemas for the Office CRUD endpoints.

These DTOs are decoupled from the ORM model — they define what the API
accepts and returns, while the model (``app.models.office.Office``) owns
the DB schema.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class OfficeCreate(BaseModel):
    """Payload for ``POST /api/v1/offices``."""

    name: str
    slug: str


class OfficeUpdate(BaseModel):
    """Payload for ``PATCH /api/v1/offices/{office_id}``.

    Slug is mutable — when provided the endpoint checks uniqueness.
    """

    name: str | None = None
    slug: str | None = None


class OfficeOut(BaseModel):
    """Response body for a single Office."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    blackboard_ref: str | None = None
    created_at: datetime
    updated_at: datetime
