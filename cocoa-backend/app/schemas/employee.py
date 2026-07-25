"""Request/response schemas for the Employee CRUD endpoints.

These DTOs are decoupled from the ORM model — they define what the API
accepts and returns, while the model (``app.models.employee.Employee``)
owns the DB schema.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

VALID_RANKS = frozenset({"intern", "researcher", "director"})


class EmployeeCreate(BaseModel):
    """Payload for ``POST /api/v1/employees``."""

    name: str
    slug: str
    rank: str = "intern"
    preset_slug: str | None = None
    display_name: str | None = None
    display_color: str | None = None

    @field_validator("rank")
    @classmethod
    def _validate_rank(cls, v: str) -> str:
        if v not in VALID_RANKS:
            allowed = ", ".join(sorted(VALID_RANKS))
            raise ValueError(
                f"Invalid rank {v!r}. Must be one of: {allowed}"
            )
        return v


class EmployeeUpdate(BaseModel):
    """Payload for ``PATCH /api/v1/employees/{employee_id}``.

    Slug is immutable — once created, an employee's slug cannot change.
    """

    name: str | None = None
    rank: str | None = None
    preset_slug: str | None = None
    display_name: str | None = None
    display_color: str | None = None

    @field_validator("rank")
    @classmethod
    def _validate_rank(cls, v: str) -> str:
        if v not in VALID_RANKS:
            allowed = ", ".join(sorted(VALID_RANKS))
            raise ValueError(
                f"Invalid rank {v!r}. Must be one of: {allowed}"
            )
        return v


class EmployeeOut(BaseModel):
    """Response body for a single Employee."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    rank: str
    preset_slug: str | None = None
    display_name: str | None = None
    display_color: str | None = None
    created_at: datetime
    updated_at: datetime
