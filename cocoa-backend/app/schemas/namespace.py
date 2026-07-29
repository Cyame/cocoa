"""Namespace schemas (PRD-v2 scenario partition)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NamespaceCreate(BaseModel):
    slug: str
    name: str
    description: str | None = None
    tags: list[str] | dict | None = None
    org_id: str | None = None


class NamespaceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    tags: list[str] | dict | None = None


class NamespaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    slug: str
    name: str
    description: str | None = None
    tags: list | dict | None = None
    created_at: datetime
    updated_at: datetime | None = None


class NamespaceOutWithStats(NamespaceOut):
    workspace_count: int = 0
    entity_count: int = 0
