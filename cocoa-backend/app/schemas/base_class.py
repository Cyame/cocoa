"""Request/response schemas for the BaseClass (L3 神职) market.

Pure DTOs — no ORM config. The list endpoint is needed for the T5
onboarding modal so it can offer pre-built roles to the user without
hard-coding them in the portal.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BaseClassOut(BaseModel):
    """Response body for a single BaseClass row.

    Used by ``GET /api/v1/base-classes`` (offset-paginated list).
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    name: str
    display_name: str | None = None
    description: str | None = None
    manifest: dict | None = None
    version: str | None = None
    tags: list[str] | None = None
    created_at: datetime
