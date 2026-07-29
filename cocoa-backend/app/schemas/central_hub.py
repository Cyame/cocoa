"""CentralHub schemas — Workspace-scoped shared collaboration surface.

> **15d-rename (2026-07-29)**: Renamed from `central_hub.py`. Class names
> `CentralHubOut` / `CentralHubUpdate` are 15d+ canonical. No back-compat
> aliases — no prod data yet.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CentralHubUpdate(BaseModel):
    """Partial update for a CentralHub's content and/or manual notes.

    ``None`` means "don't touch this field" (exclude_unset=True).
    An empty string means "clear this field".
    """

    content: str | None = None
    manual_notes: str | None = None


class CentralHubOut(BaseModel):
    """Read-only representation of a CentralHub."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    content: str | None
    manual_notes: str | None
    created_at: datetime
