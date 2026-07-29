"""Capability market (L1) list schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CapabilityMarketEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    type: str
    description: str | None = None
    config_template: dict | None = None
    tags: list[str] | None = None
    created_via: str
    source_entity_slug: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
