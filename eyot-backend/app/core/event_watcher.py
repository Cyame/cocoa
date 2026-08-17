"""EventWatcher — K8s cross-pod event dispatch bridge.

In local mode the in-process ``emit()`` already calls registered handlers. In
K8s mode, HTTP event emission persists a row in the database from another pod,
so this watcher polls those rows and dispatches them in the local process.
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
from typing import Final

from sqlalchemy import select

from app.core import events as event_module
from app.core.db import get_session_factory
from app.models.event import Event

logger = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS: Final[float] = 1.5


class EventWatcher:
    """Poll the events table and dispatch new rows to local handlers."""

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._last_seen_id = 0
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        """Start the background polling task, unless it is already running."""
        if self._task is not None and not self._task.done():
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Signal the polling task to stop and await its exit."""
        if self._task is None:
            return
        self._stopping.set()
        try:
            await asyncio.wait_for(self._task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self._task.cancel()

    async def _run(self) -> None:
        """Poll the database until shutdown is requested."""
        while not self._stopping.is_set():
            try:
                await self._poll_once()
            except Exception as error:  # noqa: BLE001, BROAD_EXCEPT_OK - worker boundary
                logger.exception(
                    "EventWatcher poll failed", extra={"error": str(error)}
                )
            try:
                await asyncio.wait_for(
                    self._stopping.wait(), timeout=POLL_INTERVAL_SECONDS
                )
            except asyncio.TimeoutError:
                pass

    async def _poll_once(self) -> None:
        """Fetch and dispatch up to 100 events newer than the last row seen."""
        async with get_session_factory()() as db:
            statement = (
                select(Event)
                .where(Event.id > self._last_seen_id)
                .order_by(Event.id.asc())
                .limit(100)
            )
            result = await db.execute(statement)
            for event in result.scalars().all():
                self._last_seen_id = max(self._last_seen_id, event.id)
                await self._dispatch(event)

    async def _dispatch(self, event: Event) -> None:
        """Dispatch one event using the same keyword contract as ``emit``."""
        payload = {
            "event": event,
            "event_type": event.type,
            "actor_type": event.actor_type,
            "actor_id": event.actor_id,
            "resource_type": event.resource_type,
            "resource_id": event.resource_id,
            "payload": event.payload,
            "request_id": event.request_id,
        }
        for pattern, handler in event_module._handlers:
            if not fnmatch.fnmatchcase(event.type, pattern):
                continue
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(**payload)
                else:
                    handler(**payload)
            except Exception as error:  # noqa: BLE001, BROAD_EXCEPT_OK - handler boundary
                logger.warning("EventWatcher handler failed", extra={"type": event.type, "error": str(error)})


# Singleton used by the application lifespan in K8s pod mode.
event_watcher = EventWatcher()
