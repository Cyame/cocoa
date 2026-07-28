"""Event-dispatched handlers for the P8 harness supervisor.

Each function handles ONE ``harness.*`` event by mutating the supervisor's
in-memory registry and (for ``checkpoint``) delegating breaker evaluation
to :mod:`app.core.harness_supervisor` (which delegates to
:mod:`app.core.harness_breakers`). Handlers NEVER write to the business
DB on a caller-owned session — the P3.5 dispatcher contract.

The ``handle_checkpoint_writes`` corollary owns its own short-lived
session to persist the per-checkpoint Blackboard summary and MemoryEntry
append-log rows that P11c wired up. The P3.5 contract is preserved: no
caller session is borrowed, no business-DB write happens on the
checkpoint caller's transaction.

Imports are deferred to break the circular dependency with
:mod:`app.core.harness_supervisor` (that module imports the handlers
back, so a top-level import of ``InstanceLoopMetrics`` would fail).
"""
from __future__ import annotations

from datetime import datetime, timezone

# Deferred inside handler bodies — see module docstring.


async def handle_checkpoint_writes(**kwargs: object) -> None:
    """Persist the P11c checkpoint side effects: Blackboard summary + MemoryEntry.

    Accepts the full :func:`app.core.events.emit` keyword envelope so the
    same function is callable from the supervisor dispatch chain
    (positional ``resource_id``/``payload``) and from a standalone
    ``register_handler("harness.checkpoint", handle_checkpoint_writes)``
    registration. Looks up the instance's active :class:`Membership` to
    discover ``office_id`` and ``employee_id`` (MemoryEntry requires an
    ``employee_id`` FK; Blackboard is keyed by ``office_id``). Skips
    silently when:

    * the instance does not exist, is soft-deleted, or has no live
      membership;
    * the loop's :class:`InstanceLoopState` is ``interrupted`` or
      ``paused`` (P9+ will surface a resume entry instead).

    Owns its own session per the P3.5 dispatcher contract; never borrows
    the caller's session. Failures are logged and swallowed — the
    runtime already returned ``token_estimate`` to the supervisor so a
    side-effect miss must not cascade.
    """
    instance_id = kwargs.get("resource_id") or kwargs.get("instance_id")
    payload = kwargs.get("payload") or {}
    explicit_summary = kwargs.get("summary") or ""
    if not isinstance(instance_id, str) or not instance_id:
        return
    iteration = int(payload.get("iteration", 0)) if isinstance(payload, dict) else 0

    from loguru import logger
    from sqlalchemy import select

    from app.core.db import get_session_factory
    from app.models.central_hub import CentralHub
    from app.models.instance import Instance
    from app.models.loop_state import InstanceLoopState, LoopStatus
    from app.models.memory import MemoryEntry, MemoryKind
    from app.models.office import Membership

    factory = get_session_factory()
    async with factory() as session:
        try:
            instance = await session.get(Instance, instance_id)
            if instance is None or instance.deleted_at is not None:
                return

            membership_result = await session.execute(
                select(Membership)
                .where(
                    Membership.instance_id == instance_id,
                    Membership.deleted_at.is_(None),
                )
                .limit(1)
            )
            membership = membership_result.scalar_one_or_none()
            if membership is None:
                return

            state_result = await session.execute(
                select(InstanceLoopState).where(
                    InstanceLoopState.instance_id == instance_id,
                    InstanceLoopState.deleted_at.is_(None),
                )
            )
            state = state_result.scalar_one_or_none()
            if state is not None and state.loop_status in {
                LoopStatus.interrupted.value,
                LoopStatus.paused.value,
            }:
                return

            text = (
                explicit_summary
                or f"Checkpoint #{iteration} completed for instance "
                   f"{instance_id[:8]}"
            )[:500]

            blackboard_result = await session.execute(
                select(CentralHub).where(
                    CentralHub.office_id == membership.office_id,
                    CentralHub.deleted_at.is_(None),
                )
            )
            blackboard = blackboard_result.scalar_one_or_none()
            if blackboard is None:
                blackboard = CentralHub(
                    office_id=membership.office_id, content=text
                )
                session.add(blackboard)
            else:
                blackboard.content = text

            session.add(
                MemoryEntry(
                    employee_id=instance.employee_id,
                    kind=MemoryKind.experience.value,
                    key=f"checkpoint_{instance_id[:8]}_{iteration}",
                    content=text,
                    source_instance_id=instance_id,
                )
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.opt(exception=True).warning(
                "checkpoint side-effect writes failed",
                instance_id=instance_id,
            )


def handle_loop_started(supervisor, instance_id: str) -> None:
    """Start a new loop — stamp wall-clock and clear counters."""
    from app.core.harness_supervisor import InstanceLoopMetrics
    supervisor._registry[instance_id] = InstanceLoopMetrics(
        wall_clock_started=datetime.now(timezone.utc),
    )


async def handle_checkpoint(supervisor, instance_id: str, payload: dict) -> None:
    """Update in-memory metrics, then check the four breakers.

    Opens a short-lived SELECT-only session for the breaker config read.
    No commit is required on this session because no writes happen on
    the read path; the trip-emit session is committed inside
    :func:`app.core.harness_breakers.trip_breaker`.
    """
    from app.core.harness_supervisor import InstanceLoopMetrics
    metrics = supervisor._registry.setdefault(
        instance_id, InstanceLoopMetrics()
    )
    metrics.continuation_count += 1
    metrics.token_estimate += int(payload.get("token_estimate", 0))
    metrics.last_checkpoint_at = datetime.now(timezone.utc)

    from app.core.db import get_session_factory
    session_factory = get_session_factory()
    async with session_factory() as session:
        await supervisor._check_breakers(instance_id, session)


def handle_continuation_injected(supervisor, instance_id: str) -> None:
    """A continuation was injected — reset the idle timer."""
    metrics = supervisor._registry.get(instance_id)
    if metrics is not None:
        metrics.last_checkpoint_at = datetime.now(timezone.utc)


def handle_loop_stopped(supervisor, instance_id: str) -> None:
    """Loop stopped — drop the in-memory registry entry."""
    supervisor._registry.pop(instance_id, None)
