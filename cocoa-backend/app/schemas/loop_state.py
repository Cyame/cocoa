"""Response schemas for harness control commands and Boulder snapshots.

All control command endpoints (interrupt/pause/resume/status/snapshot) return
typed schemas — never bare dicts — so the OpenAPI surface stays inspectable
and contract-stable across P8/P9 iterations.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InstanceLoopStateOut(BaseModel):
    """Response body for ``GET /instances/{id}/status``.

    Aggregates the DB-persisted loop state with the circuit-breaker
    configuration so the operator can see both the live counters and the
    thresholds that the Supervisor will trip against.
    """

    model_config = ConfigDict(from_attributes=True)

    instance_id: str
    loop_status: str
    continuation_count: int
    total_token_estimate: int
    last_checkpoint_at: datetime | None = None
    breaker_config: dict


class BoulderSnapshotOut(BaseModel):
    """Response body for ``POST /instances/{id}/snapshot``.

    ``captured_at`` is the server clock at the moment the snapshot was taken
    (not the checkpoint timestamp) so callers can correlate with audit events.
    """

    boulder_snapshot: dict
    continuation_count: int
    captured_at: datetime
