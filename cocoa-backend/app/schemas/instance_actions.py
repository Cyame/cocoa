"""Phase-15f instance action schemas.

DTOs for the instance-level re-sync endpoints (restart / batch-restart).
These were added to phase-15f to support the "outdated instance → re-sync
to current migration_hash" flow that the promote endpoint triggers.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RestartRequest(BaseModel):
    """Payload for ``POST /api/v1/instances/{instance_id}/restart``.

    Per PRD §13.6.7: re-sync an outdated instance to the current
    ``Employee.migration_hash``. Refuses if the instance is running
    unless ``force=true``.
    """

    reason: str | None = Field(
        default=None,
        description="Optional free-form reason recorded in the event payload.",
    )
    force: bool = Field(
        default=False,
        description="If true, restart even when status=='running'.",
    )


class RestartResultOut(BaseModel):
    """Response for ``POST /api/v1/instances/{instance_id}/restart``."""

    restarted_at: str
    instance_id: str
    old_hash: str | None
    new_hash: str | None
    status_after: str


class BatchRestartRequest(BaseModel):
    """Payload for ``POST /api/v1/instances/batch-restart``.

    Per PRD §13.6.7: bulk re-sync of multiple outdated instances. If any
    instance in the batch is currently running, the entire batch is
    rejected with 409 (the response should list the offending IDs).
    """

    instance_ids: list[str] = Field(
        ...,
        min_length=1,
        description="Instance UUIDs to re-sync.",
    )
    reason: str | None = Field(
        default=None,
        description="Optional free-form reason recorded in the event payload.",
    )


class BatchRestartResultOut(BaseModel):
    """Response for ``POST /api/v1/instances/batch-restart``."""

    restarted_count: int
    restarted_at: str
    instance_ids: list[str]
    skipped: list[str]
