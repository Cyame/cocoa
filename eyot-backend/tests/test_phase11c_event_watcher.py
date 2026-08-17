from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.event_watcher import EventWatcher, event_watcher
from app.core.events import register_handler


@pytest.mark.asyncio
async def test_poll_dispatches_to_handlers_mocked() -> None:
    """Given a new DB event, the watcher dispatches its payload to handlers."""
    event = SimpleNamespace(
        id=1,
        type="test.event",
        actor_type="system",
        actor_id=None,
        resource_type="instance",
        resource_id="resource-1",
        payload={"value": 42},
        request_id="request-1",
        created_at=datetime.now(UTC),
    )
    handler = AsyncMock()
    register_handler("test.event", handler)

    result = MagicMock()
    result.scalars.return_value.all.return_value = [event]
    session = AsyncMock()
    session.execute.return_value = result
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=None)
    session_factory = MagicMock(return_value=session_context)

    watcher = EventWatcher()
    with patch("app.core.event_watcher.get_session_factory", return_value=session_factory):
        await watcher._poll_once()

    handler.assert_awaited_once()
    assert handler.await_args.kwargs["event_type"] == "test.event"
    assert handler.await_args.kwargs["payload"] == {"value": 42}


@pytest.mark.asyncio
async def test_local_mode_no_watcher() -> None:
    """Given a watcher with a completed task, start and stop remain idempotent."""
    loop = __import__("asyncio").get_running_loop()
    completed_task = loop.create_future()
    completed_task.set_result(None)
    def fake_create_task(coroutine):
        coroutine.close()
        return completed_task

    with patch("app.core.event_watcher.asyncio.create_task", side_effect=fake_create_task):
        await event_watcher.start()
        await event_watcher.stop()
        await event_watcher.stop()
