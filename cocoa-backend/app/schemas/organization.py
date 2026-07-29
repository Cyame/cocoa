"""Organization schemas (PRD-v2 tenant root)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    name: str
    created_at: datetime
    updated_at: datetime | None = None


class OrganizationUpdate(BaseModel):
    name: str | None = None
