"""Blackboard schemas — Office-scoped shared collaboration surface."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BlackboardUpdate(BaseModel):
    """Partial update for a Blackboard's content and/or manual notes.

    ``None`` means "don't touch this field" (exclude_unset=True).
    An empty string means "clear this field".
    """

    content: str | None = None
    manual_notes: str | None = None


class BlackboardOut(BaseModel):
    """Read-only representation of a Blackboard."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    office_id: str
    content: str | None
    manual_notes: str | None
    created_at: datetime
