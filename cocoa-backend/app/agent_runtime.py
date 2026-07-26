"""Agent runtime skeleton — Boulder loop iterator (no real LLM).

P8 delivers a placeholder event-driven loop that exercises the entire
``harness.*`` event stream end-to-end:

    loop_started -> [checkpoint -> checkpoint -> ...] -> loop_stopped

Real LLM integration lands in P9+. The skeleton is sufficient for:
- P8 unit tests (Todo 11) to assert the event flow
- P9 portal integration (debug-first raw panels observe the events)

Notepad writes use ``instance.workspace_path`` (P7 generated), falling back
to a tempfile only if workspace_path is None.

The runtime also subscribes to ``HARNESS_CONTROL_SENT`` events and
self-terminates when ``action == "kill"`` arrives — the D11 control
downlink contract.
"""

from __future__ import annotations

import asyncio
import tempfile

from loguru import logger
from sqlalchemy import select

from app.core.db import get_session_factory
from app.core.event_types import (
    HARNESS_CHECKPOINT,
    HARNESS_CONTROL_SENT,
    HARNESS_LOOP_STARTED,
    HARNESS_LOOP_STOPPED,
)
from app.core.events import emit, register_handler
from app.core.harness_supervisor import supervisor
from app.core.notepad import append_to_notepad
from app.models.instance import Instance
from app.models.loop_state import InstanceLoopState, LoopStatus

_ITERATIONS: int = 10
_ITERATION_SLEEP: float = 0.2


async def _resolve_workspace_path(instance_id: str) -> str | None:
    """Read Instance.workspace_path from DB, or None if not provisioned."""
    async with get_session_factory()() as session:
        result = await session.execute(
            select(Instance).where(Instance.id == instance_id)
        )
        instance = result.scalars().first()
        if instance is None:
            return None
        return instance.workspace_path


async def run_agent_loop(instance_id: str) -> None:
    """Run the placeholder agent loop for one Instance.

    1. Resolve workspace_path (DB or tempfile fallback)
    2. Register a HARNESS_CONTROL_SENT handler that flips an internal flag
    3. Emit HARNESS_LOOP_STARTED
    4. Loop _ITERATIONS times: sleep, check stop, write notepad, emit checkpoint
    5. Emit HARNESS_LOOP_STOPPED
    6. Cleanup: deregister handler, remove from supervisor._runtime_tasks
    """
    workspace_path = await _resolve_workspace_path(instance_id)
    if workspace_path is None:
        workspace_path = tempfile.mkdtemp(prefix=f"cocoa-agent-{instance_id}-")
        logger.warning(
            "Instance has no workspace_path; using tempfile fallback",
            instance_id=instance_id,
            fallback=workspace_path,
        )

    stop_flag = asyncio.Event()

    async def _on_control(**kwargs: object) -> None:
        payload = kwargs.get("payload") or {}
        if payload.get("instance_id") == instance_id and payload.get("action") == "kill":
            stop_flag.set()

    register_handler(HARNESS_CONTROL_SENT, _on_control)

    try:
        # ---- start ----
        async with get_session_factory()() as s:
            await emit(
                HARNESS_LOOP_STARTED,
                actor_type="instance",
                actor_id=instance_id,
                resource_type="instance",
                resource_id=instance_id,
                session=s,
            )
            await s.commit()

        # ---- iteration loop ----
        for i in range(_ITERATIONS):
            if stop_flag.is_set():
                logger.info("Agent loop stopping on kill", instance_id=instance_id, iteration=i)
                break

            await asyncio.sleep(_ITERATION_SLEEP)

            # Check DB loop_status (separate kill path)
            async with get_session_factory()() as s:
                state_result = await s.execute(
                    select(InstanceLoopState).where(
                        InstanceLoopState.instance_id == instance_id,
                        InstanceLoopState.deleted_at.is_(None),
                    )
                )
                state = state_result.scalars().first()
                if state and state.loop_status in {
                    LoopStatus.interrupted.value,
                    LoopStatus.paused.value,
                }:
                    logger.info(
                        "Agent loop stopping on DB status change",
                        instance_id=instance_id,
                        loop_status=state.loop_status,
                    )
                    break

                # Notepad append
                try:
                    await append_to_notepad(
                        workspace_path,
                        "p8-bootstrap",
                        "learnings",
                        f"Checkpoint {i}",
                    )
                except Exception:
                    logger.opt(exception=True).warning(
                        "Notepad append failed",
                        instance_id=instance_id,
                        iteration=i,
                    )

                # Emit checkpoint
                await emit(
                    HARNESS_CHECKPOINT,
                    actor_type="instance",
                    actor_id=instance_id,
                    resource_type="instance",
                    resource_id=instance_id,
                    payload={
                        "token_estimate": 0,
                        "snapshot": {
                            "plan_slug": state.current_plan_ref if state else None,
                            "iteration": i,
                            "todos": [],  # skeleton: no real todos
                        },
                    },
                    session=s,
                )
                await s.commit()

        # ---- stop ----
        async with get_session_factory()() as s:
            await emit(
                HARNESS_LOOP_STOPPED,
                actor_type="instance",
                actor_id=instance_id,
                resource_type="instance",
                resource_id=instance_id,
                session=s,
            )
            await s.commit()
    finally:
        # Always remove from registry and let the handler be GC'd.
        supervisor._runtime_tasks.pop(instance_id, None)
        # Handler deregistration: register_handler only appends; we cannot
        # selectively remove. Leaving the handler in place is benign — it
        # only acts when payload["instance_id"] matches; once the loop ends
        # we set stop_flag.set() so any subsequent kill is a no-op.
        stop_flag.set()


async def start_runtime_for(instance_id: str) -> None:
    """Start the agent runtime task for *instance_id* if not already running.

    Idempotent: if a task already exists for this instance_id, this is a no-op.
    Otherwise, create an asyncio.Task and register it in supervisor._runtime_tasks.
    """
    if instance_id in supervisor._runtime_tasks:
        return
    task = asyncio.create_task(run_agent_loop(instance_id))
    supervisor._runtime_tasks[instance_id] = task
    logger.info("Agent runtime task started", instance_id=instance_id)
