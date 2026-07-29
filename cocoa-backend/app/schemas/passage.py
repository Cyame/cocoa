"""Passage schemas — Membership↔Membership only (PRD-v2)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PassageCreate(BaseModel):
    workspace_id: str
    from_membership_id: str
    to_membership_id: str
    is_active: bool = True
    edge_meta: dict | None = None


class PassageUpdate(BaseModel):
    is_active: bool | None = None
    edge_meta: dict | None = None


class PassageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    from_membership_id: str
    to_membership_id: str
    is_active: bool
    edge_meta: dict | None
    created_at: datetime
    updated_at: datetime
