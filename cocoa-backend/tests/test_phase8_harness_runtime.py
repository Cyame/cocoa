"""P8 runtime + breaker tests.

Tests for the supervisor's checkpoint flow, breaker tripping, agent
runtime skeleton, and continuation engine. Shared fixtures
(``_clear_handlers``, ``loop_state_factory``, ``office_factory``,
``employee_factory``, ``instance_factory``) live in
``tests/conftest.py``.
"""

from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.continuation import idle_check_handler
from app.core.event_types import (
    HARNESS_BREAKER_TRIPPED,
    HARNESS_CHECKPOINT,
    HARNESS_CONTINUATION_INJECTED,
    HARNESS_LOOP_STARTED,
    HARNESS_LOOP_STOPPED,
)
from app.core.events import emit
from app.core.harness_supervisor import InstanceLoopMetrics, supervisor
from app.models.event import Event
from app.models.loop_state import LoopStatus


@pytest.fixture(autouse=True)
def _raise_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.middleware.rate_limit.MAX_REQUESTS_PER_WINDOW", 100_000,
    )


@pytest_asyncio.fixture
async def wired_factory(db_url: str):
    """Bind the global session factory to the test's event loop."""
    import app.core.config as cfg
    import app.core.db as db_mod

    previous_url = cfg.settings.DATABASE_URL
    cfg.settings.DATABASE_URL = db_url
    db_mod._engine = None
    db_mod._session_factory = None
    try:
        yield
    finally:
        db_mod._engine = None
        db_mod._session_factory = None
        cfg.settings.DATABASE_URL = previous_url


async def _events(
    session: AsyncSession, event_type: str, resource_id: str,
) -> list[Event]:
    """Run a SELECT on Event by (type, resource_id) and materialize."""
    result = await session.execute(
        select(Event).where(Event.type == event_type, Event.resource_id == resource_id)
    )
    return list(result.scalars().all())


async def test_checkpoint_updates_metrics(
    wired_factory,  # noqa: ARG001
    session: AsyncSession, instance_factory, loop_state_factory,
):
    await supervisor.start()  # register harness.* handler (in test's loop)
    instance = await instance_factory()
    await loop_state_factory(instance)
    await session.commit()

    await emit(
        HARNESS_CHECKPOINT,
        actor_type="instance", actor_id=instance.id,
        resource_type="instance", resource_id=instance.id,
        payload={"token_estimate": 100}, session=session,
    )
    await session.commit()

    metrics = supervisor.get_loop_status(instance.id)
    assert metrics["continuation_count"] == 1
    assert metrics["token_estimate"] == 100


async def test_breaker_trips_on_max_continuations(
    wired_factory,  # noqa: ARG001
    session: AsyncSession, instance_factory, loop_state_factory,
):
    await supervisor.start()  # register harness.* handler (in test's loop)
    instance = await instance_factory()
    await loop_state_factory(instance, max_continuations=3)
    await session.commit()

    # `_check_breakers` uses `>=`: with max_continuations=3, on the 3rd
    # increment the breaker trips and pops the registry. Emit exactly 3
    # checkpoints so the registry stays empty afterwards.
    for _ in range(3):
        await emit(
            HARNESS_CHECKPOINT,
            actor_type="instance", actor_id=instance.id,
            resource_type="instance", resource_id=instance.id,
            payload={"token_estimate": 0}, session=session,
        )
        await session.commit()

    trip_events = await _events(session, HARNESS_BREAKER_TRIPPED, instance.id)
    assert len(trip_events) >= 1
    assert trip_events[0].payload["reason"] == "max_continuations"
    assert instance.id not in supervisor._registry  # popped on trip


async def test_breaker_trips_on_idle_timeout(
    wired_factory,  # noqa: ARG001
    session: AsyncSession, instance_factory, loop_state_factory,
):
    from app.core.queue import InMemoryTaskQueue

    instance = await instance_factory()
    old = datetime.now(timezone.utc).replace(year=2020, month=1, day=1)
    state = await loop_state_factory(
        instance,
        idle_timeout_seconds=1, last_checkpoint_at=old, loop_status="running",
    )
    # Wall-clock and continuation caps high so ONLY idle_timeout can trip
    state.max_continuations = 999999
    state.max_wall_clock_seconds = 999999
    state.max_token_estimate = 999999999
    await session.commit()

    # Pre-populate the registry with stale last_checkpoint_at (the
    # _on_harness_event path that would normally populate this is
    # bypassed here).
    supervisor._registry[instance.id] = InstanceLoopMetrics(
        continuation_count=0, token_estimate=0,
        wall_clock_started=datetime.now(timezone.utc), last_checkpoint_at=old,
    )

    queue = InMemoryTaskQueue()
    queue.register_task("idle_check", idle_check_handler)
    await queue.start()
    try:
        await idle_check_handler({"task_queue": queue})
        await asyncio.sleep(0)
    finally:
        await queue.stop()

    events = await _events(session, HARNESS_BREAKER_TRIPPED, instance.id)
    assert any(e.payload.get("reason") == "idle_timeout" for e in events), (
        f"Expected idle_timeout trip; got reasons: "
        f"{[e.payload.get('reason') for e in events]}"
    )


async def test_agent_loop_runs_checkpoints(
    wired_factory,  # noqa: ARG001
    session: AsyncSession, instance_factory, loop_state_factory,
):
    from app.agent_runtime import run_agent_loop

    instance = await instance_factory()
    instance.workspace_path = tempfile.mkdtemp(prefix="agent-test-")
    await session.commit()
    await loop_state_factory(instance, loop_status="running")
    await session.commit()

    await run_agent_loop(instance.id)

    for expected in (HARNESS_LOOP_STARTED, HARNESS_LOOP_STOPPED):
        events = await _events(session, expected, instance.id)
        assert events, f"Missing {expected}"

    checkpoints = await _events(session, HARNESS_CHECKPOINT, instance.id)
    assert checkpoints, "Expected at least one checkpoint"


async def test_agent_loop_stops_on_interrupt(
    wired_factory,  # noqa: ARG001
    session: AsyncSession, instance_factory, loop_state_factory,
):
    from app.agent_runtime import run_agent_loop

    instance = await instance_factory()
    instance.workspace_path = tempfile.mkdtemp(prefix="agent-int-")
    await session.commit()
    state = await loop_state_factory(instance, loop_status="running")
    await session.commit()

    async def flip_to_interrupted():
        await asyncio.sleep(0.5)  # let loop start
        state.loop_status = LoopStatus.interrupted.value
        await session.commit()

    flip_task = asyncio.create_task(flip_to_interrupted())
    try:
        await run_agent_loop(instance.id)
    finally:
        await flip_task

    checkpoints = await _events(session, HARNESS_CHECKPOINT, instance.id)
    assert len(checkpoints) < 10, (
        f"Expected early stop, but {len(checkpoints)} checkpoints were emitted"
    )


async def test_continuation_injected_on_timeout(
    wired_factory,  # noqa: ARG001
    session: AsyncSession, instance_factory, loop_state_factory,
):
    from app.core.queue import InMemoryTaskQueue

    instance = await instance_factory()
    old = datetime.now(timezone.utc).replace(year=2020)
    state = await loop_state_factory(
        instance,
        loop_status="running", last_checkpoint_at=old, idle_timeout_seconds=1,
    )
    # Disable breaker tripping so idle_check emits continuation_injected.
    state.max_continuations = 999999
    state.max_wall_clock_seconds = 999999
    state.max_token_estimate = 999999999
    await session.commit()

    queue = InMemoryTaskQueue()
    queue.register_task("idle_check", idle_check_handler)
    await queue.start()
    try:
        await idle_check_handler({"task_queue": queue})
        await asyncio.sleep(0)
    finally:
        await queue.stop()

    cont = (await _events(session, HARNESS_CONTINUATION_INJECTED, instance.id))[0:1]
    assert cont, "Expected continuation_injected event"
    assert cont[0].payload["plan_ref"] is None  # current_plan_ref was None
