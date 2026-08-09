"""Request/response schemas for BaseClass CRUD (PRD-v2)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from app.core.slug import KebabSlug
from app.schemas.preset import PresetManifest, validate_subagent_strategy


def _validate_manifest_subagent_strategy(manifest: dict | None) -> None:
    """Whitelist-check ``manifest.subagent_strategy`` on the API write path.

    ``BaseClass.manifest`` is stored as a bare dict (union with
    ``PresetManifest`` resolves to dict first), so the PresetManifest
    field validators never run for API payloads — the check must live on
    the create/update schemas to avoid a silent no-op (v5.1 audit).
    """
    if isinstance(manifest, dict):
        validate_subagent_strategy(manifest)


class BaseClassCreate(BaseModel):
    slug: KebabSlug
    name: str
    version: str | None = None
    manifest: dict | None = None
    has_knowledge: list[str] | None = None
    display_name: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    scope: str = "org"
    organization_id: str | None = None
    namespace_id: str | None = None

    @model_validator(mode="after")
    def _validate_manifest(self) -> "BaseClassCreate":
        _validate_manifest_subagent_strategy(self.manifest)
        return self


class BaseClassUpdate(BaseModel):
    slug: KebabSlug | None = None
    name: str | None = None
    version: str | None = None
    manifest: dict | None = None
    has_knowledge: list[str] | None = None
    display_name: str | None = None
    description: str | None = None
    tags: list[str] | None = None

    @model_validator(mode="after")
    def _validate_manifest(self) -> "BaseClassUpdate":
        _validate_manifest_subagent_strategy(self.manifest)
        return self


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
    has_knowledge: list[str] | None = None
    version: str | None = None
    tags: list[str] | None = None
    scope: str = "org"
    organization_id: str | None = None
    namespace_id: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
