"""Request/response schemas for Entity CRUD (PRD-v2)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

VALID_RANKS = frozenset({"intern", "researcher"})


class EntityCreate(BaseModel):
    name: str
    slug: str
    namespace_id: str | None = None
    rank: str = "intern"
    preset_slug: str | None = None
    display_name: str | None = None
    display_color: str | None = None
    system_prompt: str | None = None
    config_override: dict | None = None

    @field_validator("rank")
    @classmethod
    def _validate_rank(cls, v: str) -> str:
        if v not in VALID_RANKS:
            allowed = ", ".join(sorted(VALID_RANKS))
            raise ValueError(f"Invalid rank {v!r}. Must be one of: {allowed}")
        return v


class EntityUpdate(BaseModel):
    name: str | None = None
    preset_slug: str | None = None
    display_name: str | None = None
    display_color: str | None = None
    system_prompt: str | None = None
    config_override: dict | None = None


class EntityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    namespace_id: str
    name: str
    slug: str
    rank: str
    preset_slug: str | None = None
    display_name: str | None = None
    display_color: str | None = None
    system_prompt: str | None = None
    config_override: dict | None = None
    migration_hash: str | None = None
    # v4.0: read-only aggregate DTO filled from the entity_capabilities
    # junction — not a DB column and never a write truth.
    capabilities: list | dict | None = None
    is_cerebellum: bool = False
    created_at: datetime
    updated_at: datetime
