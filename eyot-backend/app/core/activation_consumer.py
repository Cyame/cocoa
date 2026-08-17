"""Consume P5 ``messaging.activation_triggered`` events to start idle agent runtimes.

P5 emits activation events for three triggers (daily_report / on_mention / intern).
For each, P8's Harness Supervisor decides whether to spin up an agent runtime:
- If the Entity has an active Instance in the workspace AND its ``loop_status``
  is ``idle``, call ``supervisor.handle_resume`` to start the loop.
- If the Entity has no Instance in this workspace, log and skip (P9+ will
  implement the lazy-create-Instance path; P8 skeleton focuses on the
  event-consume + resume path).

After each loop checkpoint, the agent runtime calls
``write_central_hub_summary`` (defined here) to update the per-workspace
CentralHub with a hardcoded summary stub and append a Memory.
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import register_handler
from app.core.harness_supervisor import supervisor
from app.models.central_hub import CentralHub
from app.models.instance import Instance, InstanceStatus
from app.models.loop_state import InstanceLoopState, LoopStatus
from app.models.memory import Memory


async def on_activation_triggered(**kwargs) -> None:
    """Handler for ``messaging.activation_triggered`` events.

    Important: ``entity_id`` comes from ``kwargs["resource_id"]`` (P5
    sets ``resource_id=str(emp.id)`` when emitting), NOT from
    ``payload["entity_id"]`` (which only carries ``trigger`` and
    ``workspace_id``).

    Trigger types: ``daily_report``, ``on_mention``, ``intern``.

    Behavior:
    1. Resolve entity_id and workspace_id from kwargs
    2. Open a fresh session (handler owns the transaction — handler is
       invoked by the in-process dispatcher, no caller session)
    3. Find the Entity's active Instance in this workspace
    4. If found AND ``InstanceLoopState.loop_status == idle``, call
       ``supervisor.handle_resume`` to start the runtime
    5. Commit
    """
    entity_id: str | None = kwargs.get("resource_id")
    payload: dict = kwargs.get("payload") or {}
    workspace_id: str | None = payload.get("workspace_id")
    trigger: str = payload.get("trigger", "unknown")

    if entity_id is None or workspace_id is None:
        logger.warning(
            "activation_triggered missing required fields",
            payload=payload,
        )
        return

    # The handler must open its own session per P3.5 contract (no caller session).
    from app.core.db import get_session_factory
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            # 1. Find active Instance for this entity in this workspace
            result = await session.execute(
                select(Instance).where(
                    Instance.entity_id == entity_id,
                    Instance.workspace_id == workspace_id,
                    Instance.deleted_at.is_(None),
                    Instance.status.in_([
                        InstanceStatus.running.value,
                        InstanceStatus.pending.value,
                        InstanceStatus.creating.value,
                        InstanceStatus.deploying.value,
                    ]),
                )
            )
            instance = result.scalars().first()
            if instance is None:
                logger.info(
                    "activation_triggered: no active instance; skipping resume",
                    entity_id=entity_id,
                    workspace_id=workspace_id,
                    trigger=trigger,
                )
                return

            # 2. Check loop_status
            state_result = await session.execute(
                select(InstanceLoopState).where(
                    InstanceLoopState.instance_id == instance.id,
                    InstanceLoopState.deleted_at.is_(None),
                )
            )
            state = state_result.scalars().first()
            # 3. If idle, resume. If no state, create idle then resume.
            if state is None:
                state = InstanceLoopState(instance_id=instance.id, loop_status=LoopStatus.idle.value)
                session.add(state)
                await session.flush()

            if state.loop_status == LoopStatus.idle.value:
                await supervisor.handle_resume(instance.id, session)
                await session.commit()
                # Trigger runtime start (idempotent)
                from app.agent_runtime import start_runtime_for
                await start_runtime_for(instance.id)
                logger.info(
                    "activation_triggered: idle instance resumed",
                    entity_id=entity_id,
                    instance_id=instance.id,
                    trigger=trigger,
                )
            else:
                logger.debug(
                    "activation_triggered: instance not idle; skipping resume",
                    entity_id=entity_id,
                    instance_id=instance.id,
                    loop_status=state.loop_status,
                    trigger=trigger,
                )
        except Exception:
            await session.rollback()
            logger.opt(exception=True).error(
                "activation_triggered handler failed",
                entity_id=entity_id,
                workspace_id=workspace_id,
                trigger=trigger,
            )


def register_activation_consumer() -> None:
    """Register the activation consumer with the in-process dispatcher.

    Call once at lifespan startup. Idempotent (P3.5 register_handler is
    append-only, so this function MUST only be called once — lifespan owns
    this).
    """
    register_handler("messaging.activation_triggered", on_activation_triggered)


async def write_central_hub_summary(
    instance_id: str,
    workspace_id: str,
    summary: str,
    session: AsyncSession,
) -> None:
    """Update the workspace's CentralHub content with the latest checkpoint summary.

    Lazy-creates the CentralHub if missing (P6 lazy-create pattern).
    Skeleton uses a hardcoded summary string (no LLM summarization yet —
    P9+ will replace with real LLM summary generation).
    """
    result = await session.execute(
        select(CentralHub).where(
            CentralHub.workspace_id == workspace_id,
            CentralHub.deleted_at.is_(None),
        )
    )
    central_hub = result.scalars().first()
    if central_hub is None:
        central_hub = CentralHub(workspace_id=workspace_id, content="")
        session.add(central_hub)
        await session.flush()
    central_hub.content = summary  # skeleton: hardcoded stub


async def append_memory_entry(
    workspace_id: str,
    key: str,
    content: str,
    session: AsyncSession,
    kind: str = "experience",
) -> None:
    """Append a Memory to the workspace's append-only memory log.

    Memory has no soft-delete semantics — pure append. Caller
    chooses ``kind`` (e.g., "experience", "decision", "lesson").
    """
    entry = Memory(
        workspace_id=workspace_id,
        kind=kind,
        key=key,
        content=content,
    )
    session.add(entry)
    await session.flush()
