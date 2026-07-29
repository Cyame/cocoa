"""Activation triggers for the messaging topology.

Three trigger types:
1. daily_report — self-sync timer via TaskQueue (P5 emits events only; P8 harness runs real logic)
2. on_mention — triggered after successful message delivery (P5 emits events only)
3. intern_hot_load — stateless invocation for intern-rank entities (creates Instance directly)
"""

from uuid import uuid4

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.core.event_types import MESSAGING_ACTIVATION_TRIGGERED
from app.core.events import emit
from app.core.queue import TaskQueue
from app.core.workspace import generate_workspace_path
from app.models.entity import Entity
from app.models.instance import Instance, InstanceStatus
from app.models.workspace import Workspace

# ---------------------------------------------------------------------------
# Module-level state for daily-report anti-duplicate
# ---------------------------------------------------------------------------

_task_queue: TaskQueue | None = None
"""Reference to the active TaskQueue, captured at registration time."""

_pending_daily_report: str | None = None
"""Task id of the currently enqueued daily_report_sync (None = not pending)."""


# ====================================================================
# A. Daily-report sync
# ====================================================================


async def _daily_report_handler(payload: dict) -> None:
    """Iterate every active Workspace and emit activation events for all running entities.

    Opens an independent session, iterates all workspaces and their entities
    via Instance records, emits activation events for each, and re-schedules
    itself for the next day.
    """
    global _pending_daily_report, _task_queue

    # Anti-duplicate: clear the pending flag so re-enqueue at end can re-set it.
    # If somehow a second handler instance fires before the first completes,
    # the flag will already be None and the second instance proceeds (safe —
    # the event is idempotent from the consumer's perspective).
    _pending_daily_report = None

    factory = get_session_factory()
    async with factory() as session:
        try:
            # Query all active (non-deleted) Workspaces
            result = await session.execute(
                select(Workspace).where(Workspace.deleted_at.is_(None))
            )
            workspaces = result.scalars().all()

            for workspace in workspaces:
                # Find Entitys with a running Instance in this Workspace
                emp_result = await session.execute(
                    select(Entity)
                    .join(Instance, Instance.entity_id == Entity.id)
                    .where(
                        Instance.workspace_id == workspace.id,
                        Instance.status == InstanceStatus.running.value,
                        Instance.deleted_at.is_(None),
                        Entity.deleted_at.is_(None),
                    )
                )
                entities = emp_result.scalars().all()

                for emp in entities:
                    await emit(
                        MESSAGING_ACTIVATION_TRIGGERED,
                        actor_type="system",
                        resource_type="entity",
                        resource_id=str(emp.id),
                        payload={
                            "trigger": "daily_report",
                            "workspace_id": str(workspace.id),
                        },
                        session=session,
                    )
                    logger.debug(
                        "Daily report activation emitted",
                        entity_id=str(emp.id),
                        workspace_id=str(workspace.id),
                    )

            await session.commit()
            logger.info(
                "Daily report sync complete",
                workspace_count=len(workspaces),
            )
        except Exception:
            await session.rollback()
            logger.exception("Daily report sync failed")
            return

    # Re-enqueue for next day (86400 seconds = 24 hours)
    if _task_queue is not None:
        _pending_daily_report = await _task_queue.enqueue(
            "daily_report_sync", delay=86400
        )


async def schedule_daily_report_sync(task_queue: TaskQueue) -> None:
    """Register and enqueue the daily-report sync task.

    Idempotent: if a ``daily_report_sync`` task is already pending this
    call is a no-op (simple flag-based anti-duplicate).
    """
    global _pending_daily_report, _task_queue
    if _pending_daily_report is not None:
        return

    _task_queue = task_queue
    task_queue.register_task("daily_report_sync", _daily_report_handler)
    _pending_daily_report = await task_queue.enqueue("daily_report_sync", delay=0)
    logger.info("Daily report sync scheduled")


# ====================================================================
# B. On-mention trigger
# ====================================================================


async def trigger_on_mention(
    session: AsyncSession,
    entity_id: str,
    workspace_id: str,
) -> None:
    """Emit an activation_triggered event for on-mention.

    Called by the directive router after a message is successfully delivered.
    P5 only emits the event; P8 harness consumes it for real sync logic.
    """
    await emit(
        MESSAGING_ACTIVATION_TRIGGERED,
        actor_type="system",
        resource_type="entity",
        resource_id=entity_id,
        payload={
            "trigger": "on_mention",
            "workspace_id": workspace_id,
        },
        session=session,
    )


# ====================================================================
# C. Intern invocation
# ====================================================================


async def handle_intern_invocation(
    session: AsyncSession,
    entity_slug: str,
    workspace_id: str,
) -> Instance | None:
    """Create or reuse an Instance for an intern entity.

    Intern entities are stateless: no Memory read/write, ephemeral
    instances.  Returns an existing running Instance if one exists, or
    creates a new one (status ``"creating"``).

    Returns
    -------
    Instance | None
        The running or newly created Instance, or ``None`` if the entity
        is not found or is not an intern.
    """
    # Look up Entity by slug
    result = await session.execute(
        select(Entity).where(
            Entity.slug == entity_slug,
            Entity.deleted_at.is_(None),
        )
    )
    emp = result.scalar_one_or_none()
    if emp is None:
        return None
    if emp.rank != "intern":
        return None

    # Check for an existing running Instance in this workspace
    result = await session.execute(
        select(Instance).where(
            Instance.entity_id == emp.id,
            Instance.workspace_id == workspace_id,
            Instance.status == InstanceStatus.running.value,
            Instance.deleted_at.is_(None),
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    # Create a fresh Instance
    instance = Instance(
        entity_id=emp.id,
        workspace_id=workspace_id,
        workspace_path=generate_workspace_path(emp.slug, str(uuid4())),
        status=InstanceStatus.creating.value,
        proxy_token=str(uuid4()),
    )
    session.add(instance)
    await session.flush()

    logger.info(
        "Intern instance created",
        entity_id=str(emp.id),
        workspace_id=workspace_id,
        instance_id=str(instance.id),
    )
    return instance
