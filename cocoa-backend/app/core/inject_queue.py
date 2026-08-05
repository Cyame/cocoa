"""Inject queue service (v4.7 H6): durable downlink from Workspace to Instances.

Rows live in ``instance_inject_queue``; the host polls pending rows, acks
delivered ones, and reports failures. Every state transition emits the
paired audit event. Per the ``app.core.events`` contract these functions
flush but never commit — the caller owns the transaction boundary.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_types import (
    HARNESS_INJECT_APPLIED,
    HARNESS_INJECT_FAILED,
    HARNESS_INJECT_REQUESTED,
    LEARNING_CAPABILITY_INJECTED,
    LEARNING_GENE_INJECTED,
)
from app.core.events import emit
from app.models.inject_queue import InjectStatus, InstanceInjectQueue
from app.schemas.internal import (
    DeliveryMode,
    InjectEnqueueRequest,
    InjectKind,
    compute_prose_length,
    validate_tldr,
)

_DEFAULT_TTL = timedelta(hours=1)
_COMPLETED_SWEEP_AGE = timedelta(days=7)
_POLL_DEFAULT_LIMIT = 20

_ACKED_MODES = frozenset({"soft_inject", "wake"})
_COMPLETED_STATUSES = (
    InjectStatus.acked.value,
    InjectStatus.failed.value,
    InjectStatus.expired.value,
)


async def _sync_queue_rows_in_session(session: AsyncSession) -> None:
    """Eagerly refresh in-session queue objects after a bulk UPDATE.

    Bulk ``update()`` with ``synchronize_session=False`` (required on
    ``AsyncSession`` — the "fetch" fallback issues sync IO and crashes with
    ``MissingGreenlet``) leaves identity-map objects stale. Lazy expiry
    does not work in async either (expired-attribute access is sync IO), so
    refresh eagerly so same-session callers always see post-UPDATE state.
    """
    for obj in list(session.identity_map.values()):
        if isinstance(obj, InstanceInjectQueue):
            await session.refresh(obj)


async def enqueue_inject(
    session: AsyncSession,
    *,
    instance_id: str,
    kind: InjectKind,
    delivery_mode: DeliveryMode,
    payload: dict,
    tldr: str | None = None,
) -> InstanceInjectQueue:
    """Validate (reusing the schemas), persist a pending row, emit requested."""
    req = InjectEnqueueRequest(kind=kind, delivery_mode=delivery_mode, tldr=tldr)
    validate_tldr(req.tldr, prose_length=compute_prose_length(payload))

    row = InstanceInjectQueue(
        instance_id=instance_id,
        kind=req.kind,
        delivery_mode=req.delivery_mode,
        payload=payload if payload is not None else {},
        status=InjectStatus.pending.value,
        expires_at=datetime.now(timezone.utc) + _DEFAULT_TTL,
    )
    session.add(row)
    await session.flush()

    await emit(
        HARNESS_INJECT_REQUESTED,
        actor_type="system",
        resource_type="instance",
        resource_id=instance_id,
        payload={
            "queue_id": row.id,
            "kind": row.kind,
            "delivery_mode": row.delivery_mode,
            "tldr": req.tldr,
        },
        session=session,
    )

    # L3 (audit-v4-design-review): learning-side injection entry events pair
    # with the harness inject downlink. A capability/gene inject enqueue also
    # records the learning-side ``learning.*_injected`` audit event.
    if row.kind == "capability_inject":
        await emit(
            LEARNING_CAPABILITY_INJECTED,
            actor_type="system",
            resource_type="instance",
            resource_id=instance_id,
            payload={
                "queue_id": row.id,
                "kind": row.kind,
                "delivery_mode": row.delivery_mode,
                "capability_ids": payload.get("capability_ids", []),
                "tldr": req.tldr,
            },
            session=session,
        )
    elif row.kind == "gene_inject":
        await emit(
            LEARNING_GENE_INJECTED,
            actor_type="system",
            resource_type="instance",
            resource_id=instance_id,
            payload={
                "queue_id": row.id,
                "kind": row.kind,
                "delivery_mode": row.delivery_mode,
                "gene_ids": payload.get("gene_ids", []),
                "tldr": req.tldr,
            },
            session=session,
        )
    return row


async def poll_pending_injects(
    session: AsyncSession, *, instance_id: str, limit: int = _POLL_DEFAULT_LIMIT
) -> list[InstanceInjectQueue]:
    """Return the oldest pending rows (FIFO by ``created_at, id``).

    Rows are flipped to ``delivered`` before returning; overdue pending
    rows are lazily marked ``expired`` in the same call.
    """
    now = datetime.now(timezone.utc)
    await session.execute(
        update(InstanceInjectQueue)
        .where(
            InstanceInjectQueue.instance_id == instance_id,
            InstanceInjectQueue.status == InjectStatus.pending.value,
            InstanceInjectQueue.expires_at <= now,
            InstanceInjectQueue.deleted_at.is_(None),
        )
        .values(status=InjectStatus.expired.value)
        .execution_options(synchronize_session=False)
    )
    await _sync_queue_rows_in_session(session)

    result = await session.execute(
        select(InstanceInjectQueue)
        .where(
            InstanceInjectQueue.instance_id == instance_id,
            InstanceInjectQueue.status == InjectStatus.pending.value,
            InstanceInjectQueue.expires_at > now,
            InstanceInjectQueue.deleted_at.is_(None),
        )
        .order_by(InstanceInjectQueue.created_at.asc(), InstanceInjectQueue.id.asc())
        .limit(limit)
    )
    rows = list(result.scalars().all())
    for row in rows:
        row.status = InjectStatus.delivered.value
    await session.flush()
    return rows


async def ack_injects(session: AsyncSession, *, queue_ids: list[str]) -> int:
    """Ack delivered rows; emit ``applied`` for soft_inject/wake. Returns count."""
    if not queue_ids:
        return 0
    result = await session.execute(
        select(InstanceInjectQueue).where(
            InstanceInjectQueue.id.in_(queue_ids),
            InstanceInjectQueue.deleted_at.is_(None),
        )
    )
    now = datetime.now(timezone.utc)
    acked = 0
    for row in result.scalars().all():
        if row.status != InjectStatus.delivered.value:
            continue
        row.status = InjectStatus.acked.value
        row.acked_at = now
        acked += 1
        if row.delivery_mode in _ACKED_MODES:
            await emit(
                HARNESS_INJECT_APPLIED,
                actor_type="system",
                resource_type="instance",
                resource_id=row.instance_id,
                payload={
                    "queue_id": row.id,
                    "kind": row.kind,
                    "delivery_mode": row.delivery_mode,
                },
                session=session,
            )
    await session.flush()
    return acked


async def mark_inject_failed(
    session: AsyncSession, *, queue_id: str, error_message: str
) -> InstanceInjectQueue | None:
    """Mark a queue row ``failed`` and emit the failure event."""
    row = await session.get(InstanceInjectQueue, queue_id)
    if row is None or row.deleted_at is not None:
        return None
    row.status = InjectStatus.failed.value
    row.error_message = error_message
    await emit(
        HARNESS_INJECT_FAILED,
        actor_type="system",
        resource_type="instance",
        resource_id=row.instance_id,
        payload={
            "queue_id": row.id,
            "kind": row.kind,
            "delivery_mode": row.delivery_mode,
            "error_message": error_message,
        },
        session=session,
    )
    await session.flush()
    return row


async def sweep_expired(session: AsyncSession) -> int:
    """Lazily mark all overdue pending rows ``expired``."""
    result = await session.execute(
        update(InstanceInjectQueue)
        .where(
            InstanceInjectQueue.status == InjectStatus.pending.value,
            InstanceInjectQueue.expires_at <= datetime.now(timezone.utc),
            InstanceInjectQueue.deleted_at.is_(None),
        )
        .values(status=InjectStatus.expired.value)
        .execution_options(synchronize_session=False)
    )
    await _sync_queue_rows_in_session(session)
    return result.rowcount or 0


async def sweep_old_completed(session: AsyncSession) -> int:
    """Soft-delete completed rows untouched for 7+ days (never physical)."""
    result = await session.execute(
        update(InstanceInjectQueue)
        .where(
            InstanceInjectQueue.status.in_(_COMPLETED_STATUSES),
            InstanceInjectQueue.updated_at
            < datetime.now(timezone.utc) - _COMPLETED_SWEEP_AGE,
            InstanceInjectQueue.deleted_at.is_(None),
        )
        .values(deleted_at=datetime.now(timezone.utc))
        .execution_options(synchronize_session=False)
    )
    await _sync_queue_rows_in_session(session)
    return result.rowcount or 0
