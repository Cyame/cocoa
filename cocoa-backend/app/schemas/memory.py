"""MemoryEntry schemas — append-only employee learning log."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.memory import MemoryKind


class MemoryEntryCreate(BaseModel):
    """Append a new immutable memory entry for an employee."""

    employee_id: str
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


class MemoryEntryOut(BaseModel):
    """Read-only representation of a MemoryEntry."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    employee_id: str
    kind: str
    key: str | None
    content: str | None
    source_instance_id: str | None
    created_at: datetime
