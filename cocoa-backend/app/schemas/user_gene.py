"""user_genes schemas (觉醒基因)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserGeneCreate(BaseModel):
    slug: str
    name: str
    kind: str = "custom"
    effect_scope: str = "org"
    description: str | None = None


class UserGeneUpdate(BaseModel):
    name: str | None = None
    effect_scope: str | None = None
    description: str | None = None


class UserGeneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    name: str
    kind: str
    effect_scope: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class UserGeneAttachRequest(BaseModel):
    user_id: str
