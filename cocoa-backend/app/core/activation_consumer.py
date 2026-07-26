"""Consume P5 ``messaging.activation_triggered`` events to start idle agent runtimes.

P5 emits activation events for three triggers (daily_report / on_mention / intern).
For each, P8's Harness Supervisor decides whether to spin up an agent runtime:
- If the Employee has an active Instance in the office AND its ``loop_status``
  is ``idle``, call ``supervisor.handle_resume`` to start the loop.
- If the Employee has no Instance in this office, log and skip (P9+ will
  implement the lazy-create-Instance path; P8 skeleton focuses on the
  event-consume + resume path).

After each loop checkpoint, the agent runtime calls
``write_blackboard_summary`` (defined here) to update the per-office
Blackboard with a hardcoded summary stub and append a MemoryEntry.
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import register_handler
from app.core.harness_supervisor import supervisor
from app.models.blackboard import Blackboard
from app.models.instance import Instance, InstanceStatus
from app.models.loop_state import InstanceLoopState, LoopStatus
from app.models.memory import MemoryEntry


async def on_activation_triggered(**kwargs) -> None:
    """Handler for ``messaging.activation_triggered`` events.

    Important: ``employee_id`` comes from ``kwargs["resource_id"]`` (P5
    sets ``resource_id=str(emp.id)`` when emitting), NOT from
    ``payload["employee_id"]`` (which only carries ``trigger`` and
    ``office_id``).

    Trigger types: ``daily_report``, ``on_mention``, ``intern``.

    Behavior:
    1. Resolve employee_id and office_id from kwargs
    2. Open a fresh session (handler owns the transaction — handler is
       invoked by the in-process dispatcher, no caller session)
    3. Find the Employee's active Instance in this office
    4. If found AND ``InstanceLoopState.loop_status == idle``, call
       ``supervisor.handle_resume`` to start the runtime
    5. Commit
    """
    employee_id: str | None = kwargs.get("resource_id")
    payload: dict = kwargs.get("payload") or {}
    office_id: str | None = payload.get("office_id")
    trigger: str = payload.get("trigger", "unknown")

    if employee_id is None or office_id is None:
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
            # 1. Find active Instance for this employee in this office
            result = await session.execute(
                select(Instance).where(
                    Instance.employee_id == employee_id,
                    Instance.office_id == office_id,
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
                    employee_id=employee_id,
                    office_id=office_id,
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
                    employee_id=employee_id,
                    instance_id=instance.id,
                    trigger=trigger,
                )
            else:
                logger.debug(
                    "activation_triggered: instance not idle; skipping resume",
                    employee_id=employee_id,
                    instance_id=instance.id,
                    loop_status=state.loop_status,
                    trigger=trigger,
                )
        except Exception:
            await session.rollback()
            logger.opt(exception=True).error(
                "activation_triggered handler failed",
                employee_id=employee_id,
                office_id=office_id,
                trigger=trigger,
            )


def register_activation_consumer() -> None:
    """Register the activation consumer with the in-process dispatcher.

    Call once at lifespan startup. Idempotent (P3.5 register_handler is
    append-only, so this function MUST only be called once — lifespan owns
    this).
    """
    register_handler("messaging.activation_triggered", on_activation_triggered)


async def write_blackboard_summary(
    instance_id: str,
    office_id: str,
    summary: str,
    session: AsyncSession,
) -> None:
    """Update the office's Blackboard content with the latest checkpoint summary.

    Lazy-creates the Blackboard if missing (P6 lazy-create pattern).
    Skeleton uses a hardcoded summary string (no LLM summarization yet —
    P9+ will replace with real LLM summary generation).
    """
    result = await session.execute(
        select(Blackboard).where(
            Blackboard.office_id == office_id,
            Blackboard.deleted_at.is_(None),
        )
    )
    blackboard = result.scalars().first()
    if blackboard is None:
        blackboard = Blackboard(office_id=office_id, content="")
        session.add(blackboard)
        await session.flush()
    blackboard.content = summary  # skeleton: hardcoded stub


async def append_memory_entry(
    office_id: str,
    key: str,
    content: str,
    session: AsyncSession,
    kind: str = "experience",
) -> None:
    """Append a MemoryEntry to the office's append-only memory log.

    MemoryEntry has no soft-delete semantics — pure append. Caller
    chooses ``kind`` (e.g., "experience", "decision", "lesson").
    """
    entry = MemoryEntry(
        office_id=office_id,
        kind=kind,
        key=key,
        content=content,
    )
    session.add(entry)
    await session.flush()
