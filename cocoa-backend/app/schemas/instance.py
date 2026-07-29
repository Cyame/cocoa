"""Request/response schemas for the Instance CRUD and action endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InstanceCreate(BaseModel):
    """Payload for ``POST /api/v1/instances``."""

    entity_id: str
    workspace_id: str
    workspace_path: str | None = None
    runtime_config: dict | None = None


class InstanceUpdate(BaseModel):
    """Payload for ``PATCH /api/v1/instances/{instance_id}``.

    Status is intentionally excluded — lifecycle transitions must go
    through dedicated action endpoints (deploy / start / restart / stop / fail).
    """

    runtime_config: dict | None = None
    workspace_path: str | None = None


class InstanceOut(BaseModel):
    """Response body for a single Instance without its proxy token."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    entity_id: str
    workspace_id: str
    workspace_path: str | None = None
    status: str
    runtime_config: dict | None = None
    created_at: datetime
    updated_at: datetime


class InstanceOutWithToken(InstanceOut):
    """Response body for Instance creation, including its proxy token."""

    proxy_token: str | None = None
