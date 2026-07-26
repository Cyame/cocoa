"""Central loop-state registry and deterministic circuit breakers (D11).

Holds an in-memory registry of one ``InstanceLoopMetrics`` per Instance.
Subscribes to ``harness.*`` events via the P3.5 in-process dispatcher and
runs four deterministic circuit breakers (max continuations / wall-clock /
token-budget / idle-timeout). Handlers ONLY update the in-memory registry —
they NEVER write to the business DB and NEVER call ``session.commit()``
on a caller-owned session (P3.5 contract: handlers do not own transaction
boundaries).

Session strategy for handlers
-----------------------------
``emit()`` (see ``app/core/events.py``) does not pass the calling session
to handlers via kwargs — handlers therefore open their own short-lived
sessions via ``get_session_factory()``:

* ``_handle_checkpoint`` opens a SELECT-only session to read breaker
  config from ``InstanceLoopState``. The session is closed on context
  exit; no commit is required because the session performed no writes.
* ``_trip_breaker`` opens its own session to emit the three trip events
  (``breaker_tripped`` / ``loop_stopped`` / ``control_sent``). The session
  is committed before close so the audit rows persist; this is a separate
  transaction owned by the handler for the trip itself, not the caller's
  transaction.

Direct mutators ``handle_interrupt / pause / resume / snapshot`` are called
by the API endpoint layer (which DOES own the transaction boundary) and
may write to the DB.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.core.errors import NotFoundError, ValidationError
from app.core.event_types import (
    HARNESS_BREAKER_TRIPPED,
    HARNESS_CHECKPOINT,
    HARNESS_CONTINUATION_INJECTED,
    HARNESS_CONTROL_SENT,
    HARNESS_INTERRUPTED,
    HARNESS_LOOP_STARTED,
    HARNESS_LOOP_STOPPED,
    HARNESS_PAUSED,
    HARNESS_RESUMED,
)
from app.core.events import emit, register_handler
from app.core.todo_enforcer import TodoEnforcerError, validate_boulder_snapshot
from app.models.loop_state import InstanceLoopState, LoopStatus


@dataclass
class InstanceLoopMetrics:
    continuation_count: int = 0
    token_estimate: int = 0
    wall_clock_started: datetime | None = None
    last_checkpoint_at: datetime | None = None


class HarnessSupervisor:
    """Singleton supervisor — one instance per process."""

    def __init__(self) -> None:
        self._registry: dict[str, InstanceLoopMetrics] = {}
        # Populated by the agent-runtime lifecycle (Todo 4); declared here
        # so shutdown() and the resume endpoint can iterate / deduplicate
        # without further wiring.
        self._runtime_tasks: dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Register the ``harness.*`` handler with the in-process dispatcher."""
        register_handler("harness.*", self._on_harness_event)
        logger.info("HarnessSupervisor started")

    async def rehydrate(self, session: AsyncSession) -> None:
        """Reload running Instance metrics from DB into the in-memory registry.

        Process-restart survival (M4 from review): after a backend restart
        the in-memory registry is empty, but the DB still carries
        ``loop_status=running`` rows with their persisted counters. This
        method repopulates the registry so breaker checks resume from the
        last persisted state.
        """
        stmt = select(InstanceLoopState).where(
            InstanceLoopState.loop_status == LoopStatus.running.value,
            InstanceLoopState.deleted_at.is_(None),
        )
        result = await session.execute(stmt)
        for state in result.scalars().all():
            self._registry[state.instance_id] = InstanceLoopMetrics(
                continuation_count=state.continuation_count,
                token_estimate=state.total_token_estimate,
                wall_clock_started=state.wall_clock_started_at,
                last_checkpoint_at=state.last_checkpoint_at,
            )
        logger.info(
            "Supervisor rehydrated", instance_count=len(self._registry)
        )

    async def shutdown(self) -> None:
        """Cancel and await all running agent runtime tasks."""
        for instance_id, task in list(self._runtime_tasks.items()):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.opt(exception=True).warning(
                    "Runtime task raised on shutdown",
                    instance_id=instance_id,
                )
        self._runtime_tasks.clear()
        logger.info("HarnessSupervisor shut down")

    # ------------------------------------------------------------------
    # handler (NO business-table writes, NO caller-session commit)
    # ------------------------------------------------------------------

    async def _on_harness_event(self, **kwargs: Any) -> None:
        """Single dispatcher for all harness.* events.

        Handler contract (P3.5 / plan §B):
        - NEVER call ``session.commit()`` on a caller-owned session.
        - NEVER mutate business tables (``Instance``, ``InstanceLoopState``).
        - ONLY update ``self._registry`` or open a short-lived session for
          SELECT-only breaker config reads and trip-event emits.
        - ``pause`` / ``resume`` / ``interrupted`` are direct API calls
          (not event-driven) — they go through ``handle_*`` mutators.
        """
        event_type: str = kwargs["event_type"]
        instance_id: str | None = kwargs.get("resource_id")
        payload: dict = kwargs.get("payload") or {}

        if instance_id is None:
            return

        if event_type == HARNESS_LOOP_STARTED:
            self._handle_loop_started(instance_id)
        elif event_type == HARNESS_CHECKPOINT:
            await self._handle_checkpoint(instance_id, payload)
        elif event_type == HARNESS_CONTINUATION_INJECTED:
            self._handle_continuation_injected(instance_id)
        elif event_type == HARNESS_LOOP_STOPPED:
            self._registry.pop(instance_id, None)
        # pause/resume/interrupted are direct API calls — not dispatched here.

    def _handle_loop_started(self, instance_id: str) -> None:
        self._registry[instance_id] = InstanceLoopMetrics(
            wall_clock_started=datetime.now(timezone.utc),
        )

    async def _handle_checkpoint(
        self, instance_id: str, payload: dict
    ) -> None:
        """Update in-memory metrics and check breakers.

        Opens a short-lived SELECT-only session for the breaker config
        read. No commit is required on this session because no writes
        happen on the read path.
        """
        metrics = self._registry.setdefault(instance_id, InstanceLoopMetrics())
        metrics.continuation_count += 1
        metrics.token_estimate += int(payload.get("token_estimate", 0))
        metrics.last_checkpoint_at = datetime.now(timezone.utc)

        session_factory = get_session_factory()
        async with session_factory() as session:
            await self._check_breakers(instance_id, session)
            # No commit — the session only ran SELECTs (and possibly the
            # trip emits, which open their own session). Closing without
            # commit is a no-op for SELECTs; the trip-emit session is
            # committed inside ``_trip_breaker``.

    def _handle_continuation_injected(self, instance_id: str) -> None:
        """A continuation was injected — reset the idle timer."""
        metrics = self._registry.get(instance_id)
        if metrics is not None:
            metrics.last_checkpoint_at = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # breakers (SELECT-only session, no commit)
    # ------------------------------------------------------------------

    async def _check_breakers(
        self, instance_id: str, session: AsyncSession
    ) -> str | None:
        """Check the four breakers; return the first tripped reason.

        Breaker check order (first trip wins):
            1. max_continuations
            2. token_budget
            3. wall_clock
            4. idle_timeout

        On trip, dispatches ``_trip_breaker`` which emits the audit chain.
        The session remains SELECT-only — trip emits open their own session.
        """
        metrics = self._registry.get(instance_id)
        if metrics is None:
            return None

        config = await self._load_breaker_config(instance_id, session)
        if config is None:
            return None

        if metrics.continuation_count >= config["max_continuations"]:
            await self._trip_breaker(instance_id, "max_continuations")
            return "max_continuations"
        if metrics.token_estimate >= config["max_token_estimate"]:
            await self._trip_breaker(instance_id, "token_budget")
            return "token_budget"
        now = datetime.now(timezone.utc)
        if metrics.wall_clock_started is not None:
            elapsed = (now - metrics.wall_clock_started).total_seconds()
            if elapsed >= config["max_wall_clock_seconds"]:
                await self._trip_breaker(instance_id, "wall_clock")
                return "wall_clock"
        if metrics.last_checkpoint_at is not None:
            idle = (now - metrics.last_checkpoint_at).total_seconds()
            if idle >= config["idle_timeout_seconds"]:
                await self._trip_breaker(instance_id, "idle_timeout")
                return "idle_timeout"
        return None

    async def _load_breaker_config(
        self, instance_id: str, session: AsyncSession
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

    async def _trip_breaker(self, instance_id: str, reason: str) -> None:
        """Emit trip + stop + control_sent. Opens and commits own session.

        This is the one place the handler owns a write transaction — a
        fresh session for the three audit events. The session is committed
        before close so the audit rows persist. After a successful commit,
        the instance is removed from the in-memory registry.
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
        # Commit succeeded — drop the in-memory entry. If commit raises
        # above, the registry entry is preserved and the next checkpoint
        # will re-attempt the trip.
        self._registry.pop(instance_id, None)
        logger.warning(
            "Breaker tripped", instance_id=instance_id, reason=reason
        )

    # ------------------------------------------------------------------
    # direct mutators (called by API endpoints, OWN the transaction)
    # ------------------------------------------------------------------

    async def handle_interrupt(
        self, instance_id: str, session: AsyncSession
    ) -> InstanceLoopState:
        """Mark loop interrupted. Emits control_sent(kill). Endpoint commits."""
        state = await self._get_state_or_404(instance_id, session)
        state.loop_status = LoopStatus.interrupted.value
        await emit(
            HARNESS_INTERRUPTED,
            actor_type="system",
            resource_type="instance",
            resource_id=instance_id,
            session=session,
        )
        await emit(
            HARNESS_CONTROL_SENT,
            actor_type="system",
            resource_type="instance",
            resource_id=instance_id,
            payload={"action": "kill", "instance_id": instance_id},
            session=session,
        )
        await session.flush()
        self._registry.pop(instance_id, None)
        return state

    async def handle_pause(
        self, instance_id: str, session: AsyncSession
    ) -> InstanceLoopState:
        state = await self._get_state_or_404(instance_id, session)
        state.loop_status = LoopStatus.paused.value
        await emit(
            HARNESS_PAUSED,
            actor_type="system",
            resource_type="instance",
            resource_id=instance_id,
            session=session,
        )
        await session.flush()
        return state

    async def handle_resume(
        self, instance_id: str, session: AsyncSession
    ) -> InstanceLoopState:
        state = await self._get_state_or_404(instance_id, session)
        state.loop_status = LoopStatus.running.value
        await emit(
            HARNESS_RESUMED,
            actor_type="system",
            resource_type="instance",
            resource_id=instance_id,
            session=session,
        )
        await session.flush()
        return state

    async def capture_snapshot(
        self, instance_id: str, session: AsyncSession
    ) -> tuple[dict, int, datetime]:
        """Validate and return the current boulder snapshot.

        Reads ``boulder_snapshot`` from ``InstanceLoopState``, validates
        it with :func:`app.core.todo_enforcer.validate_boulder_snapshot`,
        and returns ``(snapshot, continuation_count, captured_at)``.
        ``TodoEnforcerError`` is mapped to :class:`ValidationError` so
        the API endpoint layer can return HTTP 422.
        """
        state = await self._get_state_or_404(instance_id, session)
        snapshot = state.boulder_snapshot or {}
        try:
            validate_boulder_snapshot(snapshot)
        except TodoEnforcerError as e:
            raise ValidationError(
                "snapshot.invalid",
                "errors.snapshot.invalid",
                f"boulder_snapshot validation failed: {e}",
            ) from e
        metrics = self._registry.get(instance_id, InstanceLoopMetrics())
        return snapshot, metrics.continuation_count, datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------

    def get_loop_status(self, instance_id: str) -> dict:
        """Return in-memory metrics for an instance (no DB read).

        Used by the ``GET /instances/{id}/status`` endpoint. The registry
        is the source of truth for runtime counters; DB ``InstanceLoopState``
        carries the canonical ``loop_status`` which the endpoint merges in.
        """
        metrics = self._registry.get(instance_id, InstanceLoopMetrics())
        return {
            "continuation_count": metrics.continuation_count,
            "token_estimate": metrics.token_estimate,
            "wall_clock_started": metrics.wall_clock_started,
            "last_checkpoint_at": metrics.last_checkpoint_at,
        }

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    async def _get_state_or_404(
        self, instance_id: str, session: AsyncSession
    ) -> InstanceLoopState:
        result = await session.execute(
            select(InstanceLoopState).where(
                InstanceLoopState.instance_id == instance_id,
                InstanceLoopState.deleted_at.is_(None),
            )
        )
        state = result.scalars().first()
        if state is None:
            raise NotFoundError(
                "loop_state.not_found",
                "errors.loop_state.not_found",
                f"No InstanceLoopState for instance '{instance_id}'",
            )
        return state

    @property
    def runtime_tasks(self) -> dict[str, asyncio.Task]:
        return self._runtime_tasks


# Module-level singleton (plan Todo 3 line 67).
supervisor = HarnessSupervisor()
