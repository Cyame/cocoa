"""Brainstem scheduled-task runner (v4.8).

A single background loop fires due ``brainstem_schedules`` rows every 60
seconds. Multi-worker safety comes from ``FOR UPDATE SKIP LOCKED`` inside a
single transaction: each tick selects the earliest due schedules it can lock
and processes exactly those.

Delivery is strictly through the v4.7 inject queue (``enqueue_inject``) —
no third message bus.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Final

from croniter import CroniterBadCronError, croniter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.core.event_types import SCHEDULE_FIRED
from app.core.events import emit
from app.core.inject_queue import enqueue_inject
from app.models.central_hub import BrainstemSchedule

logger = logging.getLogger(__name__)

BRAINSTEM_TICK_SECONDS: Final[float] = 60.0

_DELIVERY_MODES = frozenset({"notify", "soft_inject", "wake"})


def compute_next_run_at(
    cron_expr: str, base: datetime | None = None
) -> datetime | None:
    """First cron fire after *base* (now by default); None on malformed cron."""
    base = base or datetime.now(timezone.utc)
    try:
        return croniter(cron_expr, base).get_next(datetime)
    except (CroniterBadCronError, ValueError):
        logger.warning(
            "Invalid cron expression; schedule will not fire: %s", cron_expr
        )
        return None


def _payload_tldr(payload: dict) -> str:
    """Compact, always-valid tldr (<=200 chars) for an arbitrary payload."""
    try:
        compact = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        compact = str(payload)
    return compact[:200] or "scheduled task"


async def _fire_schedule(db, schedule: BrainstemSchedule) -> None:
    """Dispatch one schedule's ``action_payload`` via the inject queue."""
    payload = dict(schedule.action_payload or {})
    instance_id = payload.get("instance_id")
    if not instance_id:
        logger.warning(
            "brainstem schedule has no instance_id; skipping: %s", schedule.id
        )
        return None
    delivery_mode = payload.get("delivery_mode", "wake")
    if delivery_mode not in _DELIVERY_MODES:
        delivery_mode = "wake"
    await enqueue_inject(
        db,
        instance_id=str(instance_id),
        kind="collab_inject",
        delivery_mode=delivery_mode,
        payload=payload,
        tldr=payload.get("tldr") or _payload_tldr(payload),
    )


async def brainstem_tick(db: AsyncSession | None = None) -> int:
    """Fire all currently-due schedules in one SKIP LOCKED transaction.

    With *db* ``None`` (the runner path) opens a fresh session from the
    global factory; tests pass their own session to stay on one event loop.
    """
    if db is not None:
        return await _tick_in_session(db)
    async with get_session_factory()() as session:
        return await _tick_in_session(session)


async def _tick_in_session(db) -> int:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(BrainstemSchedule)
        .where(
            BrainstemSchedule.enabled.is_(True),
            BrainstemSchedule.next_run_at.is_not(None),
            BrainstemSchedule.next_run_at <= now,
            BrainstemSchedule.deleted_at.is_(None),
        )
        .order_by(BrainstemSchedule.next_run_at.asc())
        .with_for_update(skip_locked=True)
    )
    due = list(result.scalars().all())
    for schedule in due:
        await _fire_schedule(db, schedule)
        schedule.last_run_at = now
        schedule.next_run_at = compute_next_run_at(schedule.cron_expr, now)
        await emit(
            SCHEDULE_FIRED,
            actor_type="system",
            resource_type="brainstem_schedule",
            resource_id=schedule.id,
            payload={
                "cron_expr": schedule.cron_expr,
                "next_run_at": (
                    schedule.next_run_at.isoformat()
                    if schedule.next_run_at
                    else None
                ),
            },
            session=db,
        )
        await db.flush()
    await db.commit()
    if due:
        logger.info("Brainstem runner fired schedules: %d", len(due))
    return len(due)


async def brainstem_runner_loop() -> None:
    """Background loop: 60s interval, ``CancelledError``-safe exit."""
    while True:
        await asyncio.sleep(BRAINSTEM_TICK_SECONDS)
        try:
            await brainstem_tick()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001, BROAD_EXCEPT_OK - worker boundary
            logger.exception("Brainstem runner tick failed")
