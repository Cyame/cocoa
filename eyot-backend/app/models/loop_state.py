"""InstanceLoopState model — per-Instance harness runtime state.

1:1 with ``Instance``. Tracks the Boulder loop status, current plan reference,
checkpoint timing, boulder snapshot, notepad pointers, and the four
deterministic circuit-breaker configuration values that the Harness Supervisor
reads to kill runaway loops.
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class LoopStatus(str, Enum):
    """Harness runtime states for an Instance.

    Independent of :class:`app.models.instance.InstanceStatus` (which tracks
    infrastructure lifecycle).  P7 ``Instance.status`` and P8 ``LoopStatus``
    are orthogonal; P8 deliberately does NOT mutate Instance.status when the
    breaker trips — Instance.status remains ``running`` and the operator (or
    P7's stop/delete endpoint) is the only path that flips it.

    States:
        idle: No loop is currently active for this instance.
        running: Boulder loop is iterating and emitting checkpoints.
        paused: Loop is suspended; resumes from last boulder_snapshot.
        interrupted: Loop was killed by breaker or external control command.
        completed: Loop finished cleanly (all todos completed).
        failed: Loop terminated due to unrecoverable error.
    """

    idle = "idle"
    running = "running"
    paused = "paused"
    interrupted = "interrupted"
    completed = "completed"
    failed = "failed"


class InstanceLoopState(BaseModel, Base):
    """Per-instance harness runtime state.

    One row per active (non-deleted) Instance — ``uq_loop_states_instance``
    partial unique index enforces 1:1 cardinality on the active set.

    Circuit-breaker configuration lives here so the in-memory Supervisor
    registry can read defaults from a single source of truth on startup.
    """

    __tablename__ = "instance_loop_states"
    __table_args__ = (
        Index(
            "uq_loop_states_instance",
            "instance_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    instance_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("instances.id"), nullable=False
    )
    loop_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=LoopStatus.idle.value
    )
    current_plan_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    continuation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_token_estimate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wall_clock_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_checkpoint_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    boulder_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notepad_refs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    max_continuations: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    max_wall_clock_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    max_token_estimate: Mapped[int] = mapped_column(Integer, nullable=False, default=100000)
    idle_timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)

    def __repr__(self) -> str:
        cls = type(self).__name__
        return (
            f"<{cls} {self.id!r} instance={self.instance_id!r}"
            f" loop_status={self.loop_status!r}"
            f" continuation_count={self.continuation_count}>"
        )
