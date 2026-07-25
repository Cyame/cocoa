"""Request/response schemas for the EmployeePreset CRUD endpoints.

These DTOs are decoupled from the ORM model — they define what the API
accepts and returns, while the model (``app.models.employee.EmployeePreset``)
owns the DB schema.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EmployeePresetCreate(BaseModel):
    """Payload for ``POST /api/v1/employee-presets``."""

    slug: str
    name: str
    version: str | None = None
    manifest: dict | None = None


class EmployeePresetUpdate(BaseModel):
    """Payload for ``PATCH /api/v1/employee-presets/{preset_id}``.

    Slug is immutable — once created, a preset's slug cannot change.
    """

    name: str | None = None
    version: str | None = None
    manifest: dict | None = None


class EmployeePresetOut(BaseModel):
    """Response body for a single EmployeePreset."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    name: str
    version: str | None = None
    manifest: dict | None = None
    created_at: datetime
    updated_at: datetime
