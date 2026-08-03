"""Request/response schemas for BaseClass CRUD (PRD-v2)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from app.schemas.preset import PresetManifest


class BaseClassCreate(BaseModel):
    slug: str
    name: str
    version: str | None = None
    manifest: dict | None = None
    display_name: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    scope: str = "org"
    organization_id: str | None = None
    namespace_id: str | None = None


class BaseClassUpdate(BaseModel):
    name: str | None = None
    version: str | None = None
    manifest: dict | None = None
    display_name: str | None = None
    description: str | None = None
    tags: list[str] | None = None


class PresetManifestOut(PresetManifest):
    """Out variant — accepts ``None`` and falls back to defaults."""

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def _coerce_none(cls, data: object) -> object:
        if data is None:
            return {}
        return data


class BaseClassOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    name: str
    display_name: str | None = None
    description: str | None = None
    manifest: dict | PresetManifestOut | None = None
    version: str | None = None
    tags: list[str] | None = None
    scope: str = "org"
    organization_id: str | None = None
    namespace_id: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
