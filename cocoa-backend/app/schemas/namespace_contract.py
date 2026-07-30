"""NamespaceContract (契印) schemas — PRD-v3.4."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NamespaceContractCreate(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=36)
    role: str = Field(default="viewer", pattern="^(owner|editor|viewer)$")
    permissions: dict | None = None


class NamespaceContractUpdate(BaseModel):
    role: str | None = Field(default=None, pattern="^(owner|editor|viewer)$")
    permissions: dict | None = None


class NamespaceContractOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    namespace_id: str
    user_id: str
    role: str
    permissions: dict | None
    created_at: datetime
    updated_at: datetime
