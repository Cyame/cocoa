"""Deterministic circuit breakers (D11) — extracted from harness_supervisor.

Breaker check order (first trip wins): max_continuations, token_budget,
wall_clock, idle_timeout. :class:`HarnessBreakers` is stateless — it takes
the metrics snapshot + loaded config as arguments and returns the first
tripped reason. On trip it calls :func:`trip_breaker` which emits the
audit chain (breaker_tripped / loop_stopped / control_sent) and commits
its own short-lived session — handlers never own caller transactions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.core.event_types import (
    HARNESS_BREAKER_TRIPPED,
    HARNESS_CONTROL_SENT,
    HARNESS_LOOP_STOPPED,
)
from app.core.events import emit
from app.models.loop_state import InstanceLoopState

if TYPE_CHECKING:
    from app.core.harness_supervisor import InstanceLoopMetrics


async def trip_breaker(instance_id: str, reason: str) -> None:
    """Emit trip + stop + control_sent. Opens and commits own session.

    The one place the handler owns a write transaction — a fresh session
    for the three audit events. The session is committed before close so
    the audit rows persist. The supervisor's caller is responsible for
    removing the in-memory registry entry after a successful trip.
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        await emit(
            HARNESS_BREAKER_TRIPPED,
            actor_type="system",
            resource_type="instance",
            resource_id=instance_id,
            payload={"reason": reason, "instance_id": instance_id},
            session=session,
        )
        await emit(
            HARNESS_LOOP_STOPPED,
            actor_type="system",
            resource_type="instance",
            resource_id=instance_id,
            payload={"reason": reason, "instance_id": instance_id},
            session=session,
        )
        await emit(
            HARNESS_CONTROL_SENT,
            actor_type="system",
            resource_type="instance",
            resource_id=instance_id,
            payload={
                "action": "kill",
                "instance_id": instance_id,
                "reason": reason,
            },
            session=session,
        )
        await session.commit()
    logger.warning(
        "Breaker tripped", instance_id=instance_id, reason=reason
    )


class HarnessBreakers:
    """Stateless evaluator of the four deterministic circuit breakers."""

    @staticmethod
    async def load_breaker_config(
        instance_id: str, session: AsyncSession
    ) -> dict | None:
        """Read breaker configuration from ``InstanceLoopState``.

        Returns ``None`` when no active loop state exists for the instance
        — the caller treats this as "skip breaker check" rather than an
        error.
        """
        result = await session.execute(
            select(InstanceLoopState).where(
                InstanceLoopState.instance_id == instance_id,
                InstanceLoopState.deleted_at.is_(None),
            )
        )
        state = result.scalars().first()
        if state is None:
            return None
        return {
            "max_continuations": state.max_continuations,
            "max_wall_clock_seconds": state.max_wall_clock_seconds,
            "max_token_estimate": state.max_token_estimate,
            "idle_timeout_seconds": state.idle_timeout_seconds,
        }

    @staticmethod
    async def check_breakers(
        instance_id: str,
        session: AsyncSession,
        metrics: InstanceLoopMetrics,
        config: dict,
    ) -> str | None:
        """Return the first tripped reason, or ``None`` if all pass."""
        if metrics.continuation_count >= config["max_continuations"]:
            await trip_breaker(instance_id, "max_continuations")
            return "max_continuations"
        if metrics.token_estimate >= config["max_token_estimate"]:
            await trip_breaker(instance_id, "token_budget")
            return "token_budget"
        now = datetime.now(timezone.utc)
        if metrics.wall_clock_started is not None:
            elapsed = (now - metrics.wall_clock_started).total_seconds()
            if elapsed >= config["max_wall_clock_seconds"]:
                await trip_breaker(instance_id, "wall_clock")
                return "wall_clock"
        if metrics.last_checkpoint_at is not None:
            idle = (now - metrics.last_checkpoint_at).total_seconds()
            if idle >= config["idle_timeout_seconds"]:
                await trip_breaker(instance_id, "idle_timeout")
                return "idle_timeout"
        return None
