"""Central loop-state registry and event dispatcher (D11).

Handler logic lives in :mod:`app.core.harness_handlers`. Circuit-breaker
evaluation lives in :mod:`app.core.harness_breakers`. Direct mutators are
called by the API endpoint layer (which OWNS the transaction boundary).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.core.event_types import (
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
from app.core.harness_breakers import HarnessBreakers
from app.core.harness_handlers import (
    handle_checkpoint,
    handle_continuation_injected,
    handle_loop_started,
    handle_loop_stopped,
)
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
        self._runtime_tasks: dict[str, asyncio.Task] = {}

    async def start(self) -> None:
        register_handler("harness.*", self._on_harness_event)
        logger.info("HarnessSupervisor started")

    async def rehydrate(self, session: AsyncSession) -> None:
        """Reload running Instance metrics from DB into the registry."""
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
                    "Runtime task raised on shutdown", instance_id=instance_id
                )
        self._runtime_tasks.clear()
        logger.info("HarnessSupervisor shut down")

    async def _on_harness_event(self, **kwargs: object) -> None:
        event_type: str = kwargs["event_type"]
        instance_id: str | None = kwargs.get("resource_id")
        if instance_id is None:
            return
        payload: dict = kwargs.get("payload") or {}

        if event_type == HARNESS_LOOP_STARTED:
            handle_loop_started(self, instance_id)
        elif event_type == HARNESS_CHECKPOINT:
            await handle_checkpoint(self, instance_id, payload)
        elif event_type == HARNESS_CONTINUATION_INJECTED:
            handle_continuation_injected(self, instance_id)
        elif event_type == HARNESS_LOOP_STOPPED:
            handle_loop_stopped(self, instance_id)

    async def _check_breakers(self, instance_id: str, session: AsyncSession) -> str | None:
        """Delegate to :class:`HarnessBreakers`; pop registry on trip."""
        metrics = self._registry.get(instance_id)
        if metrics is None:
            return None
        config = await HarnessBreakers.load_breaker_config(
            instance_id, session
        )
        if config is None:
            return None
        reason = await HarnessBreakers.check_breakers(
            instance_id, session, metrics, config
        )
        if reason is not None:
            # Commit succeeded inside trip_breaker — drop the in-memory entry.
            # If commit raises above, the registry entry is preserved and the
            # next checkpoint will re-attempt the trip.
            self._registry.pop(instance_id, None)
        return reason

    async def _set_loop_status(
        self,
        instance_id: str,
        new_status: str,
        event_type: str,
        session: AsyncSession,
    ) -> InstanceLoopState:
        """Fetch, mutate, emit, flush — used by handle_pause/resume."""
        state = await self._get_state_or_404(instance_id, session)
        state.loop_status = new_status
        await emit(
            event_type,
            actor_type="system",
            resource_type="instance",
            resource_id=instance_id,
            session=session,
        )
        await session.flush()
        return state

    async def handle_interrupt(self, instance_id: str, session: AsyncSession) -> InstanceLoopState:
        state = await self._set_loop_status(
            instance_id, LoopStatus.interrupted.value, HARNESS_INTERRUPTED,
            session,
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

    async def handle_pause(self, instance_id: str, session: AsyncSession) -> InstanceLoopState:
        return await self._set_loop_status(
            instance_id, LoopStatus.paused.value, HARNESS_PAUSED, session
        )

    async def handle_resume(self, instance_id: str, session: AsyncSession) -> InstanceLoopState:
        return await self._set_loop_status(
            instance_id, LoopStatus.running.value, HARNESS_RESUMED, session
        )

    async def capture_snapshot(self, instance_id: str, session: AsyncSession) -> tuple[dict, int, datetime]:
        """Validate and return the current boulder snapshot."""
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

    def get_loop_status(self, instance_id: str) -> dict:
        metrics = self._registry.get(instance_id, InstanceLoopMetrics())
        return {
            "continuation_count": metrics.continuation_count,
            "token_estimate": metrics.token_estimate,
            "wall_clock_started": metrics.wall_clock_started,
            "last_checkpoint_at": metrics.last_checkpoint_at,
        }

    async def _get_state_or_404(self, instance_id: str, session: AsyncSession) -> InstanceLoopState:
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


supervisor = HarnessSupervisor()
