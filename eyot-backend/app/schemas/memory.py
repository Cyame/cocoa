"""Memory schemas — append-only entity learning log."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.memory import MemoryKind


class MemoryCreate(BaseModel):
    """Append a new immutable memory entry for an entity."""

    entity_id: str
    kind: str
    key: str | None = None
    content: str | None = None
    source_instance_id: str | None = None

    @field_validator("kind")
    @classmethod
    def kind_must_be_valid(cls, v: str) -> str:
        allowed = {e.value for e in MemoryKind}
        if v not in allowed:
            msg = f"kind must be one of {sorted(allowed)}, got {v!r}"
            raise ValueError(msg)
        return v


class MemoryOut(BaseModel):
    """Read-only representation of a Memory."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    entity_id: str
    kind: str
    key: str | None
    content: str | None
    source_instance_id: str | None
    created_at: datetime
