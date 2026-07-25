"""Integration tests for the P3.5 observability layer.

Covers loguru JSON logging, Event model persistence, emit() dispatch,
TaskQueue roundtrip/delay, event type constants, and lifecycle event emission.
"""

import asyncio
import io
import json

from loguru import logger
from sqlalchemy import select
from starlette.testclient import TestClient

from app.core.event_types import (
    HARNESS_BREAKER_TRIPPED,
    HARNESS_CHECKPOINT,
    HARNESS_CONTINUATION_INJECTED,
    HARNESS_LOOP_STARTED,
    HARNESS_LOOP_STOPPED,
    SYSTEM_SHUTDOWN,
    SYSTEM_STARTUP,
)
from app.core.events import _handlers, emit, register_handler
from app.core.queue import InMemoryTaskQueue
from app.models.event import Event

# ---------------------------------------------------------------------------
# Test 1: JSON logging carries request_id
# ---------------------------------------------------------------------------


async def test_logging_json_contains_request_id(client: TestClient):
    """Add a JSON sink after lifespan, hit /health, verify request_id in logs.

    The sink must be added AFTER the TestClient context is entered because
    lifespan's ``configure_logging()`` calls ``logger.remove()`` which would
    strip any sink added before the context is entered.
    """
    sink = io.StringIO()
    handler_id = logger.add(sink, serialize=True)
    try:
        response = client.get("/health")
        assert response.status_code == 200

        request_id = response.headers.get("x-request-id")
        assert request_id is not None

        output = sink.getvalue()
        lines = [line for line in output.strip().split("\n") if line.strip()]
        assert len(lines) > 0, "Expected at least one JSON log line"

        found = False
        for line in lines:
            record = json.loads(line)
            extra = record.get("record", {}).get("extra", {})
            if extra.get("request_id") == request_id:
                found = True
                break

        assert found, f"request_id {request_id} not found in any log line"
    finally:
        logger.remove(handler_id)


# ---------------------------------------------------------------------------
# Test 2: Event model insert and query
# ---------------------------------------------------------------------------


async def test_event_model_persist(session):
    """Write an Event row and read it back — all 7 data fields must match."""
    event = Event(
        type="test.action",
        actor_type="user",
        actor_id="user-123",
        resource_type="instance",
        resource_id="inst-456",
        payload={"key": "value"},
        request_id="req-abc",
    )
    session.add(event)
    await session.flush()

    result = await session.execute(select(Event).where(Event.id == event.id))
    row = result.scalar_one()

    assert row.type == "test.action"
    assert row.actor_type == "user"
    assert row.actor_id == "user-123"
    assert row.resource_type == "instance"
    assert row.resource_id == "inst-456"
    assert row.payload == {"key": "value"}
    assert row.request_id == "req-abc"


# ---------------------------------------------------------------------------
# Test 3: emit() persists event and notifies handler
# ---------------------------------------------------------------------------


async def test_emit_persists_and_notifies(session):
    """emit() writes the event row and calls the registered handler.

    Handler list is saved and restored to avoid leaking into other tests.
    """
    handler_called = False

    async def my_handler(event, **kwargs):
        nonlocal handler_called
        handler_called = True

    original = list(_handlers)
    try:
        register_handler("system.*", my_handler)

        event = await emit(
            "system.test",
            actor_type="system",
            session=session,
        )
        await session.commit()

        assert handler_called, "Handler should have been called"
        assert event.type == "system.test"
        assert event.actor_type == "system"

        # Verify the row is persisted
        result = await session.execute(select(Event).where(Event.id == event.id))
        row = result.scalar_one()
        assert row.type == "system.test"
    finally:
        _handlers.clear()
        _handlers.extend(original)


# ---------------------------------------------------------------------------
# Test 4: emit() isolates handler exceptions
# ---------------------------------------------------------------------------


async def test_emit_handler_exception_isolated(session):
    """emit() must not propagate handler exceptions; event row still persists."""
    original = list(_handlers)
    try:
        async def failing_handler(event, **kwargs):
            raise RuntimeError("boom")

        register_handler("system.*", failing_handler)

        # emit() should NOT raise despite the handler blowing up.
        event = await emit(
            "system.test",
            actor_type="system",
            session=session,
        )
        await session.commit()

        result = await session.execute(select(Event).where(Event.id == event.id))
        row = result.scalar_one()
        assert row.type == "system.test"
    finally:
        _handlers.clear()
        _handlers.extend(original)


# ---------------------------------------------------------------------------
# Test 5: TaskQueue roundtrip (enqueue → consume)
# ---------------------------------------------------------------------------


async def test_taskqueue_roundtrip():
    """Enqueue a task and poll until the worker consumes it."""
    result: dict = {}

    async def handler(payload: dict) -> None:
        result["called"] = True
        result["payload"] = payload

    queue = InMemoryTaskQueue()
    queue.register_task("test.roundtrip", handler)
    await queue.start()

    try:
        task_id = await queue.enqueue("test.roundtrip", payload={"x": 1})
        assert task_id is not None

        # Poll for the worker to process the task.
        for _ in range(50):  # 5 s max
            if result.get("called") is True:
                break
            await asyncio.sleep(0.1)
        else:
            raise TimeoutError("Task was not consumed within 5 s")

        assert result["called"] is True
        assert result["payload"] == {"x": 1}
    finally:
        await queue.stop()


# ---------------------------------------------------------------------------
# Test 6: TaskQueue delay
# ---------------------------------------------------------------------------


async def test_taskqueue_delay():
    """A delayed task must not be consumed before its delay, but is after."""
    result: dict = {}

    async def handler(payload: dict) -> None:
        result["called"] = True
        result["called_at"] = asyncio.get_running_loop().time()

    queue = InMemoryTaskQueue()
    queue.register_task("test.delay", handler)
    await queue.start()

    try:
        await queue.enqueue("test.delay", delay=0.2, payload={})

        # At 0.1 s the task should NOT be consumed yet.
        await asyncio.sleep(0.1)
        assert result.get("called") is not True, "Task consumed too early (0.1 s)"

        # Wait long enough for the delay to expire plus processing time.
        await asyncio.sleep(0.25)
        assert result.get("called") is True, "Task should be consumed after 0.2 s delay"
    finally:
        await queue.stop()


# ---------------------------------------------------------------------------
# Test 7: Event type constants
# ---------------------------------------------------------------------------


async def test_event_types_constants():
    """All 7 event type constants exist and are dot-separated strings."""
    constants = [
        SYSTEM_STARTUP,
        SYSTEM_SHUTDOWN,
        HARNESS_LOOP_STARTED,
        HARNESS_CHECKPOINT,
        HARNESS_CONTINUATION_INJECTED,
        HARNESS_LOOP_STOPPED,
        HARNESS_BREAKER_TRIPPED,
    ]
    assert len(constants) == 7

    for c in constants:
        assert isinstance(c, str), f"Expected str, got {type(c)}"
        assert "." in c, f"Expected dot-separated, got {c!r}"
        assert not c.startswith("."), f"Should not start with dot: {c!r}"
        assert not c.endswith("."), f"Should not end with dot: {c!r}"


# ---------------------------------------------------------------------------
# Test 8: Lifespan emits system.startup
# ---------------------------------------------------------------------------


async def test_lifecycle_events(client: TestClient, session):
    """After TestClient lifespan, the cloned DB has a system.startup event.

    The ``client`` fixture enters the TestClient context (lifespan fires),
    which emits ``system.startup`` to the test's cloned database.
    The ``session`` fixture creates a separate engine to the same cloned DB.
    """
    result = await session.execute(
        select(Event).where(Event.type == "system.startup")
    )
    rows = result.scalars().all()
    assert len(rows) == 1, f"Expected 1 system.startup event, got {len(rows)}"
    event = rows[0]
    assert event.actor_type == "system"
    assert event.type == "system.startup"
