"""Introduce-entity schema — PRD-v3.4."""

from __future__ import annotations

from pydantic import BaseModel, Field


class IntroduceEntityRequest(BaseModel):
    entity_id: str = Field(..., min_length=1, max_length=36)
