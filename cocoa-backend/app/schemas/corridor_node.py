"""Request/response schemas for CorridorNode CRUD endpoints.

DTOs are decoupled from the ORM model — they define what the API
accepts and returns, while the model
(``app.models.corridor_node.CorridorNode``) owns the DB schema.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

CorridorNodeStatusLiteral = Literal["active", "paused", "archived"]


class CorridorNodeCreate(BaseModel):
    """Payload for ``POST /api/v1/learning/corridor-nodes``."""

    office_id: str
    posx: int = 0
    posy: int = 0
    display_name: str
    glow_color: str | None = None
    status: CorridorNodeStatusLiteral = "active"

    @field_validator("display_name")
    @classmethod
    def _trim_display_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("display_name must not be blank")
        return v

    @field_validator("glow_color")
    @classmethod
    def _validate_glow_color(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not (v.startswith("#") and len(v) == 7):
            raise ValueError("glow_color must be a 7-char hex string like #10b981")
        return v


class CorridorNodeUpdate(BaseModel):
    """Payload for ``PATCH /api/v1/learning/corridor-nodes/{id}``.

    All fields are optional — only provided fields are updated.
    """

    posx: int | None = None
    posy: int | None = None
    display_name: str | None = None
    glow_color: str | None = None
    status: CorridorNodeStatusLiteral | None = None

    @field_validator("display_name")
    @classmethod
    def _trim_display_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("display_name must not be blank")
        return v

    @field_validator("glow_color")
    @classmethod
    def _validate_glow_color(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not (v.startswith("#") and len(v) == 7):
            raise ValueError("glow_color must be a 7-char hex string like #10b981")
        return v


class CorridorNodeOut(BaseModel):
    """Response body for a single CorridorNode."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    office_id: str
    posx: int
    posy: int
    display_name: str
    glow_color: str | None
    status: CorridorNodeStatusLiteral
    created_by: str | None
    created_at: datetime
    updated_at: datetime


class CorridorNodeListOut(BaseModel):
    """Cursor-paginated list response for ``GET /api/v1/learning/corridor-nodes``."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    items: list[CorridorNodeOut]
    next_cursor: str | None = None
    total: int | None = None
