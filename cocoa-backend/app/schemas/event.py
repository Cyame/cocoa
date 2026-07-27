"""Event schemas — read-only audit log response.

The events table is append-only; only ``EventOut`` is exposed. The events
endpoint serves debug panels (P9 Todo 3, Todo 10, Todo 11) that need to
inspect the audit stream without mutating it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class EventOut(BaseModel):
    """Read-only representation of an audit :class:`~app.models.event.Event`.

    Mirrors the 9 persisted columns; ``payload`` is returned as-is (JSONB).
    The audit log has no soft-delete (``deleted_at`` is always NULL), no
    write endpoint, and no PATCH/DELETE — events are write-once.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
    actor_type: str
    actor_id: str | None
    resource_type: str | None
    resource_id: str | None
    payload: dict[str, Any]
    request_id: str | None
    created_at: datetime
