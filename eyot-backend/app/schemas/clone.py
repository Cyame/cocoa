"""Request schema for clone operations (v4.4)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.slug import KebabSlug


class CloneRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    slug: KebabSlug | None = Field(default=None, max_length=255)
