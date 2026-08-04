"""v4.7 H6 inject-queue foundation tests.

Covers the queue service contract (enqueue FIFO ordering, poll marking
``delivered``, ack + ``harness.inject_applied`` events, lazy expiry sweep,
failure marking, old-completed soft-delete sweep, soft-delete filtering)
and the V47-10 tldr hard validation (tldr <= 200 chars; prose > 240 chars
requires a non-empty tldr, else 400 with the message_key).

Every DB-touching test uses the conftest per-test cloned database — never
``cocoa_dev``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.errors import CocoaError
from app.core.event_types import (
    HARNESS_INJECT_APPLIED,
    HARNESS_INJECT_FAILED,
    HARNESS_INJECT_REQUESTED,
    HARNESS_REPORT_RECEIVED,
    LEARNING_CAPABILITY_INJECTED,
    LEARNING_GENE_INJECTED,
)
from app.core.inject_queue import (
    ack_injects,
    enqueue_inject,
    mark_inject_failed,
    poll_pending_injects,
    sweep_expired,
    sweep_old_completed,
)
from app.models.event import Event
from app.models.inject_queue import InjectStatus, InstanceInjectQueue
from app.schemas.internal import (
    InjectEnqueueRequest,
    ReportRequest,
    compute_prose_length,
)

_OLD = datetime.now(timezone.utc) - timedelta(days=8)
_ONE_HOUR = timedelta(hours=1)


async def _enqueue(session, instance_id: str, **overrides) -> InstanceInjectQueue:
    params = {
        "instance_id": instance_id,
        "kind": "collab_inject",
        "delivery_mode": "notify",
        "payload": {"seq": 1},
        "tldr": "test tldr",
    }
    params.update(overrides)
    return await enqueue_inject(session, **params)


# ---------------------------------------------------------------------------
# Event constants
# ---------------------------------------------------------------------------


def test_event_constants_importable() -> None:
    """The four v4.7 inject/report constants exist with locked values."""
    assert HARNESS_INJECT_REQUESTED == "harness.inject_requested"
    assert HARNESS_INJECT_APPLIED == "harness.inject_applied"
    assert HARNESS_INJECT_FAILED == "harness.inject_failed"
    assert HARNESS_REPORT_RECEIVED == "harness.report_received"
    # Legacy v4.6 learning constants stay untouched.
    assert LEARNING_CAPABILITY_INJECTED == "learning.capability_injected"
    assert LEARNING_GENE_INJECTED == "learning.gene_injected"


# ---------------------------------------------------------------------------
# enqueue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enqueue_creates_row_and_emits_requested(session, instance_factory) -> None:
    """Enqueue persists a pending row with 1h TTL and emits the requested event."""
    inst = await instance_factory()
    row = await enqueue_inject(
        session,
        instance_id=inst.id,
        kind="collab_inject",
        delivery_mode="soft_inject",
        payload={"text": "hello", "refs": ["a"]},
        tldr="short tldr",
    )

    assert row.status == InjectStatus.pending.value
    assert row.payload == {"text": "hello", "refs": ["a"]}
    ttl = (row.expires_at - row.created_at).total_seconds()
    assert ttl == pytest.approx(_ONE_HOUR.total_seconds(), abs=5)

    ev = (
        await session.execute(
            select(Event).where(
                Event.type == HARNESS_INJECT_REQUESTED,
                Event.resource_id == inst.id,
            )
        )
    ).scalar_one()
    assert ev.actor_type == "system"
    assert ev.resource_type == "instance"
    assert ev.payload == {
        "queue_id": row.id,
        "kind": "collab_inject",
        "delivery_mode": "soft_inject",
        "tldr": "short tldr",
    }


@pytest.mark.asyncio
async def test_enqueue_validation_rejects_bad_literals(session, instance_factory) -> None:
    """Unknown kind / delivery_mode are rejected by the schema layer."""
    inst = await instance_factory()
    with pytest.raises(Exception):
        await enqueue_inject(
            session, instance_id=inst.id, kind="file_touch", delivery_mode="notify", payload={}
        )
    with pytest.raises(Exception):
        await enqueue_inject(
            session, instance_id=inst.id, kind="collab_inject", delivery_mode="broadcast", payload={}
        )


# ---------------------------------------------------------------------------
# poll
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_poll_fifo_order_and_marks_delivered(session, instance_factory) -> None:
    """Poll returns pending rows oldest-first and flips them to delivered."""
    inst = await instance_factory()
    ids: list[str] = []
    for i in range(3):
        row = await _enqueue(session, inst.id, payload={"seq": i})
        ids.append(row.id)

    picked = await poll_pending_injects(session, instance_id=inst.id)
    assert [r.id for r in picked] == ids
    assert all(r.status == InjectStatus.delivered.value for r in picked)

    # Second poll sees nothing new — delivered rows are excluded.
    assert await poll_pending_injects(session, instance_id=inst.id) == []


@pytest.mark.asyncio
async def test_poll_respects_limit(session, instance_factory) -> None:
    inst = await instance_factory()
    for i in range(3):
        await _enqueue(session, inst.id, payload={"seq": i})

    picked = await poll_pending_injects(session, instance_id=inst.id, limit=2)
    assert len(picked) == 2
    assert all(r.status == InjectStatus.delivered.value for r in picked)


@pytest.mark.asyncio
async def test_soft_deleted_row_not_polled(session, instance_factory) -> None:
    """Soft-deleted rows never surface in poll."""
    inst = await instance_factory()
    row = await _enqueue(session, inst.id)
    row.soft_delete()
    await session.flush()

    assert await poll_pending_injects(session, instance_id=inst.id) == []


# ---------------------------------------------------------------------------
# ack
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ack_marks_acked_and_emits_applied_for_soft_inject(session, instance_factory) -> None:
    """Ack of a delivered soft_inject row flips to acked + emits applied."""
    inst = await instance_factory()
    row = await _enqueue(session, inst.id, delivery_mode="soft_inject")
    await poll_pending_injects(session, instance_id=inst.id)

    n = await ack_injects(session, queue_ids=[row.id])
    assert n == 1
    assert row.status == InjectStatus.acked.value
    assert row.acked_at is not None

    ev = (
        await session.execute(select(Event).where(Event.type == HARNESS_INJECT_APPLIED))
    ).scalar_one()
    assert ev.payload == {
        "queue_id": row.id,
        "kind": "collab_inject",
        "delivery_mode": "soft_inject",
    }


@pytest.mark.asyncio
async def test_ack_notify_mode_does_not_emit_applied(session, instance_factory) -> None:
    """Only soft_inject / wake acks produce the applied event."""
    inst = await instance_factory()
    row = await _enqueue(session, inst.id, delivery_mode="notify")
    await poll_pending_injects(session, instance_id=inst.id)

    n = await ack_injects(session, queue_ids=[row.id])
    assert n == 1
    assert row.status == InjectStatus.acked.value

    result = await session.execute(select(Event).where(Event.type == HARNESS_INJECT_APPLIED))
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_ack_skips_non_delivered_rows(session, instance_factory) -> None:
    """Ack only flips rows currently in delivered state."""
    inst = await instance_factory()
    delivered_row = await _enqueue(session, inst.id)
    await poll_pending_injects(session, instance_id=inst.id)
    pending_row = await _enqueue(session, inst.id)

    n = await ack_injects(session, queue_ids=[pending_row.id, delivered_row.id])
    assert n == 1
    assert pending_row.status == InjectStatus.pending.value
    assert delivered_row.status == InjectStatus.acked.value


# ---------------------------------------------------------------------------
# failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_inject_failed_sets_error_and_emits(session, instance_factory) -> None:
    inst = await instance_factory()
    row = await _enqueue(session, inst.id, delivery_mode="wake")

    await mark_inject_failed(session, queue_id=row.id, error_message="boom")
    assert row.status == InjectStatus.failed.value
    assert row.error_message == "boom"

    ev = (
        await session.execute(select(Event).where(Event.type == HARNESS_INJECT_FAILED))
    ).scalar_one()
    assert ev.payload["queue_id"] == row.id
    assert ev.payload["error_message"] == "boom"


# ---------------------------------------------------------------------------
# expiry / cleanup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_poll_lazily_expires_overdue_pending(session, instance_factory) -> None:
    """Overdue pending rows are marked expired during poll and not returned."""
    inst = await instance_factory()
    expired = InstanceInjectQueue(
        instance_id=inst.id,
        kind="collab_inject",
        delivery_mode="notify",
        payload={},
        status=InjectStatus.pending.value,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    session.add(expired)
    fresh = await _enqueue(session, inst.id)
    await session.flush()

    picked = await poll_pending_injects(session, instance_id=inst.id)
    assert [r.id for r in picked] == [fresh.id]
    assert expired.status == InjectStatus.expired.value


@pytest.mark.asyncio
async def test_sweep_expired_marks_all_overdue_pending(session, instance_factory) -> None:
    inst = await instance_factory()
    overdue = InstanceInjectQueue(
        instance_id=inst.id,
        kind="collab_inject",
        delivery_mode="notify",
        payload={},
        status=InjectStatus.pending.value,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    session.add(overdue)
    active = await _enqueue(session, inst.id)
    await session.flush()

    await sweep_expired(session)
    assert overdue.status == InjectStatus.expired.value
    assert active.status == InjectStatus.pending.value


@pytest.mark.asyncio
async def test_sweep_old_completed_soft_deletes_only_old(session, instance_factory) -> None:
    """Completed rows older than 7d are soft-deleted; fresh ones are kept."""
    inst = await instance_factory()
    old_acked = InstanceInjectQueue(
        instance_id=inst.id,
        kind="collab_inject",
        delivery_mode="notify",
        payload={},
        status=InjectStatus.acked.value,
        updated_at=_OLD,
    )
    recent_failed = InstanceInjectQueue(
        instance_id=inst.id,
        kind="gene_inject",
        delivery_mode="wake",
        payload={},
        status=InjectStatus.failed.value,
    )
    session.add_all([old_acked, recent_failed])
    await session.flush()

    n = await sweep_old_completed(session)
    assert n == 1
    assert old_acked.deleted_at is not None
    assert recent_failed.deleted_at is None
    assert recent_failed.status == InjectStatus.failed.value


# ---------------------------------------------------------------------------
# V47-10 tldr hard validation
# ---------------------------------------------------------------------------


def test_prose_length_deterministic() -> None:
    """compute_prose_length sums payload text/body + report list strings."""
    assert compute_prose_length(None) == 0
    assert compute_prose_length({}) == 0
    payload = {
        "text": "abc",  # 3
        "body": "defg",  # 4
        "unrelated": "x" * 999,  # ignored — not text/body
        "report": {
            "outcome": "ok",
            "changes": ["aa", "bbbb"],  # 6
            "validation": ["c"],  # 1
            "blockers": [],  # 0
        },
    }
    assert compute_prose_length(payload) == 14


def test_tldr_too_long_rejected_by_schema() -> None:
    """tldr > 200 chars fails with the tldr_too_long message_key."""
    with pytest.raises(CocoaError) as exc_info:
        InjectEnqueueRequest(kind="collab_inject", delivery_mode="notify", tldr="x" * 201)
    assert exc_info.value.message_key == "errors.internal.tldr_too_long"
    assert exc_info.value.status_code == 400

    with pytest.raises(CocoaError) as exc_info:
        ReportRequest(outcome="ok", tldr="x" * 201)
    assert exc_info.value.message_key == "errors.internal.tldr_too_long"


def test_tldr_200_chars_accepted() -> None:
    """Exactly 200 chars is allowed."""
    req = InjectEnqueueRequest(kind="collab_inject", delivery_mode="notify", tldr="x" * 200)
    assert req.tldr == "x" * 200


@pytest.mark.asyncio
async def test_prose_over_240_requires_tldr_at_enqueue(session, instance_factory) -> None:
    """Payload prose > 240 chars without tldr is rejected with 400 + message_key."""
    inst = await instance_factory()
    big = {"body": "x" * 241}

    with pytest.raises(CocoaError) as exc_info:
        await enqueue_inject(
            session, instance_id=inst.id, kind="collab_inject", delivery_mode="notify", payload=big
        )
    assert exc_info.value.message_key == "errors.internal.tldr_required"
    assert exc_info.value.status_code == 400

    # With a non-empty tldr the same payload is accepted.
    row = await enqueue_inject(
        session,
        instance_id=inst.id,
        kind="collab_inject",
        delivery_mode="notify",
        payload=big,
        tldr="tl",
    )
    assert row.status == InjectStatus.pending.value


@pytest.mark.asyncio
async def test_prose_under_240_accepts_missing_tldr(session, instance_factory) -> None:
    inst = await instance_factory()
    row = await enqueue_inject(
        session, instance_id=inst.id, kind="collab_inject", delivery_mode="notify", payload={}
    )
    assert row.status == InjectStatus.pending.value


def test_report_prose_requires_tldr() -> None:
    """ReportRequest with > 240 chars of changes/validation/blockers needs tldr."""
    with pytest.raises(CocoaError) as exc_info:
        ReportRequest(outcome="ok", changes=["x" * 241])
    assert exc_info.value.message_key == "errors.internal.tldr_required"

    ok = ReportRequest(outcome="ok", changes=["x" * 241], tldr="tl")
    assert ok.tldr == "tl"

    # Text and body fields also count toward the prose budget via payload.
    with pytest.raises(CocoaError) as exc_info:
        InjectEnqueueRequest(
            kind="collab_inject",
            delivery_mode="notify",
            report={"outcome": "ok", "changes": ["y" * 241]},
        )
    assert exc_info.value.message_key == "errors.internal.tldr_required"
