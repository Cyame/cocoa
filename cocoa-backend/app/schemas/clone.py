"""Request schema for clone operations (v4.4)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CloneRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    slug: str | None = Field(default=None, max_length=255)
