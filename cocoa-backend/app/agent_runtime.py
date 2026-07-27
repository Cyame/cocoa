"""Agent runtime skeleton — Boulder loop iterator (no real LLM).

P8 delivers a placeholder event-driven loop that exercises the entire
``harness.*`` event stream end-to-end:

    loop_started -> [checkpoint -> checkpoint -> ...] -> loop_stopped

Real LLM integration lands in P9+. Notepad writes use
``instance.workspace_path`` (P7 generated), falling back to a tempfile
only if workspace_path is None. The runtime subscribes to
``HARNESS_CONTROL_SENT`` and self-terminates on ``action == "kill"``
(D11 control downlink contract).

P11c dual-mode dispatch
-----------------------
Mode is selected once per loop via
``app.agent_runtime.k8s_adapter.is_k8s_pod_mode()``:

- **Local mode** (default): in-process ``emit()`` +
  ``register_handler(HARNESS_CONTROL_SENT, ...)`` (P8 contract
  preserved). The per-iteration DB read of
  ``InstanceLoopState.loop_status`` stays the canonical interrupt /
  pause kill path.

- **K8s pod mode** (``COCOA_POD_MODE=true``): HTTP ``emit_event()`` to
  ``/api/v1/internal/events/emit`` + periodic ``poll_control()`` polling
  the D11 downlink. K8s pods have no direct database access, so the
  DB-status check is skipped — the control polling loop is the
  canonical kill path. K8s-mode ``HARNESS_CHECKPOINT`` payloads carry
  the ``proxy_token`` so the backend can attribute the event.
"""

from __future__ import annotations

import asyncio
import tempfile

from loguru import logger
from sqlalchemy import select

from app.agent_runtime.k8s_adapter import (
    emit_event,
    get_proxy_token,
    is_k8s_pod_mode,
    poll_control,
)
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
_POLL_INTERVAL: float = 1.0


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

    Mode is selected via ``is_k8s_pod_mode()`` at start:

    * Local → ``register_handler(HARNESS_CONTROL_SENT, ...)`` flips the
      stop flag on a kill payload.
    * K8s → spawn a polling task calling ``poll_control(last_seen_id)``
      every ``_POLL_INTERVAL`` seconds and sets the stop flag when
      ``payload.action == "kill"`` arrives.

    Then emit ``HARNESS_LOOP_STARTED``, loop ``_ITERATIONS`` times
    (sleep, stop check, notepad write [local only], emit checkpoint),
    emit ``HARNESS_LOOP_STOPPED``, and clean up.
    """
    k8s_mode = is_k8s_pod_mode()
    workspace_path = await _resolve_workspace_path(instance_id)
    if workspace_path is None:
        workspace_path = tempfile.mkdtemp(prefix=f"cocoa-agent-{instance_id}-")
        logger.warning(
            "Instance has no workspace_path; using tempfile fallback",
            instance_id=instance_id,
            fallback=workspace_path,
        )

    stop_flag = asyncio.Event()
    last_seen_id: int = 0
    control_task: asyncio.Task | None = None

    if k8s_mode:
        async def _poll_control_loop() -> None:
            nonlocal last_seen_id
            while not stop_flag.is_set():
                try:
                    events = await poll_control(last_seen_id)
                except Exception:
                    logger.opt(exception=True).warning(
                        "poll_control failed; will retry",
                        instance_id=instance_id,
                    )
                    events = []
                for event in events:
                    eid = event.get("id")
                    if isinstance(eid, int):
                        last_seen_id = max(last_seen_id, eid)
                    payload = event.get("payload") or {}
                    if payload.get("action") == "kill":
                        logger.info(
                            "Agent loop stopping on polled kill",
                            instance_id=instance_id,
                        )
                        stop_flag.set()
                        return
                await asyncio.sleep(_POLL_INTERVAL)

        control_task = asyncio.create_task(_poll_control_loop())
    else:
        async def _on_control(**kwargs: object) -> None:
            payload = kwargs.get("payload") or {}
            if payload.get("instance_id") == instance_id and payload.get("action") == "kill":
                stop_flag.set()

        register_handler(HARNESS_CONTROL_SENT, _on_control)

    try:
        if k8s_mode:
            await emit_event(
                HARNESS_LOOP_STARTED,
                actor_type="instance", actor_id=instance_id,
                resource_type="instance", resource_id=instance_id,
                payload={},
            )
        else:
            async with get_session_factory()() as s:
                await emit(
                    HARNESS_LOOP_STARTED,
                    actor_type="instance", actor_id=instance_id,
                    resource_type="instance", resource_id=instance_id,
                    session=s,
                )
                await s.commit()

        for i in range(_ITERATIONS):
            if stop_flag.is_set():
                logger.info(
                    "Agent loop stopping on kill",
                    instance_id=instance_id, iteration=i,
                )
                break

            await asyncio.sleep(_ITERATION_SLEEP)

            if k8s_mode:
                # K8s pods lack direct DB access — emit the checkpoint
                # over HTTP and let the backend attribute via proxy_token.
                await emit_event(
                    HARNESS_CHECKPOINT,
                    actor_type="instance", actor_id=instance_id,
                    resource_type="instance", resource_id=instance_id,
                    payload={
                        "iteration": i,
                        "instance_id": instance_id,
                        "proxy_token": get_proxy_token() or "",
                    },
                )
                continue

            # Local mode: P8 contract — read loop_status, write notepad,
            # and emit checkpoint inside a single session so the
            # ``state.current_plan_ref`` snapshot stays accurate.
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
                        instance_id=instance_id, loop_status=state.loop_status,
                    )
                    break

                try:
                    await append_to_notepad(
                        workspace_path, "p8-bootstrap", "learnings",
                        f"Checkpoint {i}",
                    )
                except Exception:
                    logger.opt(exception=True).warning(
                        "Notepad append failed",
                        instance_id=instance_id, iteration=i,
                    )

                await emit(
                    HARNESS_CHECKPOINT,
                    actor_type="instance", actor_id=instance_id,
                    resource_type="instance", resource_id=instance_id,
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

        if k8s_mode:
            await emit_event(
                HARNESS_LOOP_STOPPED,
                actor_type="instance", actor_id=instance_id,
                resource_type="instance", resource_id=instance_id,
                payload={},
            )
        else:
            async with get_session_factory()() as s:
                await emit(
                    HARNESS_LOOP_STOPPED,
                    actor_type="instance", actor_id=instance_id,
                    resource_type="instance", resource_id=instance_id,
                    session=s,
                )
                await s.commit()
    finally:
        supervisor._runtime_tasks.pop(instance_id, None)
        if control_task is not None:
            control_task.cancel()
            try:
                await control_task
            except asyncio.CancelledError:
                pass
        # Always set the flag so any pending handler call becomes a no-op.
        stop_flag.set()


async def start_runtime_for(instance_id: str) -> None:
    """Start the agent runtime task for *instance_id* if not already running.

    Idempotent: if a task already exists, this is a no-op. Otherwise
    create an asyncio.Task and register it in ``supervisor._runtime_tasks``.
    """
    if instance_id in supervisor._runtime_tasks:
        return
    task = asyncio.create_task(run_agent_loop(instance_id))
    supervisor._runtime_tasks[instance_id] = task
    logger.info("Agent runtime task started", instance_id=instance_id)
