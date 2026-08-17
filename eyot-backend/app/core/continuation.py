"""Idle-check continuation engine for the Harness Supervisor.

A periodic TaskQueue task that scans all ``loop_status=running`` instances
and emits ``harness.continuation_injected`` for any whose last checkpoint
is older than ``idle_timeout_seconds``.

The actual continuation logic (resume the loop from the last
``boulder_snapshot``) lives in P9+. For P8 the event is emitted and the
agent runtime picks it up on the next iteration (P8 skeleton does not
react — see Todo 4 line "P8 skeleton: continuation_injected only persisted,
not triggering real recovery").
"""
from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select

from app.core.db import get_session_factory
from app.core.event_types import HARNESS_CONTINUATION_INJECTED
from app.core.events import emit
from app.core.harness_supervisor import supervisor
from app.models.loop_state import InstanceLoopState, LoopStatus


async def idle_check_handler(payload: dict) -> None:
    """Periodic task: check each running Instance for idle timeout.

    Behavior:
    1. Open a fresh session
    2. Query all InstanceLoopState rows with loop_status=running
    3. For each, FIRST call ``supervisor._check_breakers`` (which evaluates
       ALL four breakers including idle_timeout — this is where idle trips
       fire when checkpoint is stale)
    4. Then, if NOT tripped and last_checkpoint_at is older than
       idle_timeout_seconds, emit ``harness.continuation_injected``
    5. Commit
    6. Re-enqueue via the task_queue reference stored on the payload
       (the worker passes ``{"task_queue": queue}`` so we can self-reschedule)

    Payload contract:
        payload["task_queue"]: InMemoryTaskQueue — required for rescheduling
    """
    task_queue = payload.get("task_queue")
    if task_queue is None:
        logger.warning("idle_check_handler called without task_queue; skipping reschedule")
        return

    session_factory = get_session_factory()
    async with session_factory() as session:
        stmt = select(InstanceLoopState).where(
            InstanceLoopState.loop_status == LoopStatus.running.value,
            InstanceLoopState.deleted_at.is_(None),
        )
        result = await session.execute(stmt)
        states = list(result.scalars().all())

        for state in states:
            # 1. Breaker check first — if idle_timeout trips we don't emit continuation
            reason = await supervisor._check_breakers(state.instance_id, session)
            if reason is not None:
                logger.info(
                    "idle_check: breaker tripped, skipping continuation_injected",
                    instance_id=state.instance_id,
                    reason=reason,
                )
                continue

            # 2. Emit continuation_injected if stale
            if state.last_checkpoint_at is None:
                # Never had a checkpoint — skip (agent runtime must emit one first)
                continue
            idle_seconds = (
                datetime.now(timezone.utc) - state.last_checkpoint_at
            ).total_seconds()
            if idle_seconds > state.idle_timeout_seconds:
                await emit(
                    HARNESS_CONTINUATION_INJECTED,
                    actor_type="system",
                    resource_type="instance",
                    resource_id=state.instance_id,
                    payload={
                        "instance_id": state.instance_id,
                        "plan_ref": state.current_plan_ref,
                        "idle_seconds": idle_seconds,
                    },
                    session=session,
                )
                logger.info(
                    "idle_check: continuation_injected emitted",
                    instance_id=state.instance_id,
                    idle_seconds=idle_seconds,
                )

        await session.commit()

    # 3. Self-reschedule for 30 seconds later
    await task_queue.enqueue("idle_check", delay=30, payload={"task_queue": task_queue})
