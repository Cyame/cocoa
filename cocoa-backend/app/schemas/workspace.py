"""Request/response schemas for Workspace CRUD (PRD-v2)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WorkspaceCreate(BaseModel):
    name: str
    slug: str
    namespace_id: str | None = None


class WorkspaceUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None


class WorkspaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    namespace_id: str
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime
