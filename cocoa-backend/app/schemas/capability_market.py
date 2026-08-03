"""Capability market (L1) schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, computed_field

CapabilityTypeLiteral = Literal["skill", "tool", "mcp", "lsp", "command"]
ScopeLiteral = Literal["system", "org", "namespace"]


class CapabilityMarketEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    type: str
    description: str | None = None
    config_template: dict | None = None
    tags: list[str] | None = None
    scope: str
    organization_id: str | None = None
    namespace_id: str | None = None
    created_by_user_id: str | None = None
    created_via: str
    source_entity_slug: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def readonly(self) -> bool:
        return self.scope == "system"


class CapabilityMarketEntryCreate(BaseModel):
    name: str
    type: CapabilityTypeLiteral = "skill"
    description: str | None = None
    config_template: dict | None = None
    tags: list[str] | None = None
    scope: ScopeLiteral = "org"
    organization_id: str | None = None
    namespace_id: str | None = None


class CapabilityMarketEntryUpdate(BaseModel):
    name: str | None = None
    type: CapabilityTypeLiteral | None = None
    description: str | None = None
    config_template: dict | None = None
    tags: list[str] | None = None
