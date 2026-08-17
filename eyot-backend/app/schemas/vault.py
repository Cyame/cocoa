"""Vault schemas — archival storage per Workspace."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class VaultOut(BaseModel):
    """Read-only representation of a Vault (1:1 with an Workspace)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    created_at: datetime


class VaultEntryOut(BaseModel):
    """Read-only representation of an archived artifact entry."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    vault_id: str
    source_type: str
    source_ref: str | None
    archived_key: str | None
    archived_at: datetime | None
    created_at: datetime
