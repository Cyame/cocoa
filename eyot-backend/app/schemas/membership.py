"""Request/response schemas for Membership CRUD endpoints.

These DTOs are decoupled from the ORM model — they define what the API
accepts and returns, while the model (``app.models.workspace.Membership``)
owns the DB schema.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator


class MembershipCreate(BaseModel):
    """Payload for ``POST /api/v1/messaging/memberships``.

    Exactly one of ``user_id`` or ``instance_id`` must be provided.
    """

    workspace_id: str
    user_id: str | None = None
    instance_id: str | None = None
    posx: int = 0
    posy: int = 0

    @model_validator(mode="after")
    def check_exclusive_fk(self) -> MembershipCreate:
        user = self.user_id
        instance = self.instance_id
        if (user is None) == (instance is None):
            raise ValueError("Exactly one of user_id or instance_id must be set")
        return self


class MembershipUpdate(BaseModel):
    """Payload for ``PATCH /api/v1/messaging/memberships/{membership_id}``.

    All fields are optional — only provided fields are updated.
    """

    posx: int | None = None
    posy: int | None = None


class MembershipOut(BaseModel):
    """Response body for a single Membership."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    user_id: str | None
    instance_id: str | None
    posx: int
    posy: int
    permissions: dict | None
    created_at: datetime
    updated_at: datetime
    # Populated for instance seats (迷失者) when listing topology data.
    entity_slug: str | None = None
    entity_name: str | None = None
    # Populated for user seats (觉醒者). username ≈ slug; nickname ≈ display_name.
    username: str | None = None
    nickname: str | None = None
