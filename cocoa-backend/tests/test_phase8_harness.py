"""P8 Harness integration tests.

17 tests covering migration round-trip, notepad engine, todo-enforcer,
Harness Supervisor + circuit breakers, control command endpoints, agent
runtime skeleton, continuation engine, and P5 regression check.
"""

from __future__ import annotations

import asyncio
import tempfile
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

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
from app.core.notepad import VALID_NOTEPADS, append_to_notepad, read_notepad
from app.core.todo_enforcer import TodoEnforcerError, validate_boulder_snapshot
from app.models.employee import Employee
from app.models.event import Event
from app.models.instance import Instance, InstanceStatus
from app.models.loop_state import InstanceLoopState, LoopStatus
from app.models.office import Membership, MembershipRole, Office
from app.models.user import User

# ---------------------------------------------------------------------------
# Test isolation: clear global handler list + supervisor registry
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _raise_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.middleware.rate_limit.MAX_REQUESTS_PER_WINDOW",
        100_000,
    )


@pytest_asyncio.fixture(autouse=True)
async def _clear_handlers():
    """Reset global handler list and supervisor registry around every test.

    Critical per C4 review: without this, harness.* handlers pile up across
    tests, causing state from previous tests to leak (e.g., stale
    ``supervisor._registry`` entries, leftover event handlers).
    """
    import app.core.activation as act_mod
    import app.core.events as ev_mod

    ev_mod._handlers.clear()
    supervisor._registry.clear()
    supervisor._runtime_tasks.clear()
    act_mod._pending_daily_report = None
    act_mod._task_queue = None
    yield
    ev_mod._handlers.clear()
    supervisor._registry.clear()
    supervisor._runtime_tasks.clear()


@pytest_asyncio.fixture
async def wired_factory(db_url: str):
    """Configure the global session factory to the per-test DB URL.

    Critical for tests that invoke ``run_agent_loop`` or
    ``idle_check_handler`` — both call ``get_session_factory()`` which
    relies on the global engine being bound to the *test's* event loop.
    Without this, lifespan-based engines (created on a different loop via
    TestClient) cause "Future attached to a different loop" errors.
    """
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


# ---------------------------------------------------------------------------
# Auth + factory fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def auth_token(client: TestClient) -> str:
    client.post(
        "/api/v1/auth/register",
        json={
            "username": "p8_test",
            "email": "p8_test@test.com",
            "password": "password123",
        },
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "p8_test", "password": "password123"},
    )
    return resp.json()["access_token"]


@pytest.fixture
def auth_headers(auth_token: str) -> dict:
    return {"Authorization": f"Bearer {auth_token}"}


@pytest_asyncio.fixture
async def auth_user_id(session: AsyncSession) -> str:
    """Return the user_id of the registered p8_test user."""
    result = await session.execute(select(User).where(User.username == "p8_test"))
    user = result.scalars().first()
    assert user is not None
    return user.id


def _setup_office_and_membership(
    client: TestClient,
    token: str,
    user_id: str,
    office_name: str = "P8 Office",
    office_slug: str = "p8-office",
) -> str:
    """Create an office via HTTP and link the user as owner. Return office_id."""
    h = {"Authorization": f"Bearer {token}"}
    office = client.post(
        "/api/v1/offices",
        headers=h,
        json={"name": office_name, "slug": office_slug},
    ).json()
    client.post(
        "/api/v1/messaging/memberships",
        headers=h,
        json={
            "office_id": office["id"],
            "user_id": user_id,
            "hex_q": 0,
            "hex_r": 0,
            "role": "owner",
        },
    )
    return office["id"]


def _create_employee(client: TestClient, token: str, slug: str, name: str) -> str:
    h = {"Authorization": f"Bearer {token}"}
    return client.post(
        "/api/v1/employees",
        headers=h,
        json={"name": name, "slug": slug},
    ).json()["id"]


@pytest_asyncio.fixture
async def office_factory(session: AsyncSession):
    async def _make(**overrides) -> Office:
        defaults = {
            "name": overrides.pop("name", "Test Office"),
            "slug": overrides.pop("slug", f"test-office-{uuid.uuid4().hex[:8]}"),
        }
        defaults.update(overrides)
        office = Office(**defaults)
        session.add(office)
        await session.flush()
        return office

    return _make


@pytest_asyncio.fixture
async def employee_factory(session: AsyncSession):
    async def _make(**overrides) -> Employee:
        defaults = {
            "name": overrides.pop("name", "Test Employee"),
            "slug": overrides.pop("slug", f"test-emp-{uuid.uuid4().hex[:8]}"),
        }
        defaults.update(overrides)
        emp = Employee(**defaults)
        session.add(emp)
        await session.flush()
        return emp

    return _make


@pytest_asyncio.fixture
async def instance_factory(session: AsyncSession, employee_factory, office_factory):
    async def _make(**overrides) -> Instance:
        if "employee_id" not in overrides:
            emp = await employee_factory()
            overrides["employee_id"] = emp.id
        if "office_id" not in overrides:
            office = await office_factory()
            overrides["office_id"] = office.id
        defaults = {
            "status": InstanceStatus.creating.value,
            "proxy_token": str(uuid.uuid4()),
        }
        defaults.update(overrides)
        inst = Instance(**defaults)
        session.add(inst)
        await session.flush()
        return inst

    return _make


@pytest_asyncio.fixture
async def loop_state_factory(session: AsyncSession):
    """Create an InstanceLoopState row tied to an existing Instance."""

    async def _make(instance: Instance, **overrides) -> InstanceLoopState:
        defaults = {
            "instance_id": instance.id,
            "loop_status": LoopStatus.idle.value,
            "continuation_count": 0,
            "total_token_estimate": 0,
        }
        defaults.update(overrides)
        state = InstanceLoopState(**defaults)
        session.add(state)
        await session.flush()
        return state

    return _make


# ---------------------------------------------------------------------------
# Test 1: Migration round-trip
# ---------------------------------------------------------------------------


async def test_loop_state_migration_roundtrip(session: AsyncSession):
    """instance_loop_states table exists with all 13 custom columns + 4 base."""
    result = await session.execute(
        text("SELECT column_name FROM information_schema.columns WHERE table_name = 'instance_loop_states'")
    )
    cols = {row[0] for row in result.fetchall()}
    expected = {
        "id",
        "created_at",
        "updated_at",
        "deleted_at",  # BaseModel
        "instance_id",
        "loop_status",
        "current_plan_ref",
        "continuation_count",
        "total_token_estimate",
        "wall_clock_started_at",
        "last_checkpoint_at",
        "boulder_snapshot",
        "notepad_refs",
        "max_continuations",
        "max_wall_clock_seconds",
        "max_token_estimate",
        "idle_timeout_seconds",
    }
    assert expected.issubset(cols), f"Missing columns: {expected - cols}"


# ---------------------------------------------------------------------------
# Test 2: Notepad append + read
# ---------------------------------------------------------------------------


async def test_append_and_read_notepad():
    workspace = tempfile.mkdtemp(prefix="test-notepad-")
    path = await append_to_notepad(workspace, "test-plan", "learnings", "first entry")
    assert path.endswith("learnings.md")
    content = await read_notepad(workspace, "test-plan", "learnings")
    assert "first entry" in content
    assert "[" in content  # timestamp bracket
    assert VALID_NOTEPADS == ["learnings", "issues", "decisions", "problems"]


# ---------------------------------------------------------------------------
# Test 3: Notepad rejects invalid names
# ---------------------------------------------------------------------------


async def test_invalid_notepad_name_rejected():
    workspace = tempfile.mkdtemp()
    with pytest.raises(ValueError, match="invalid notepad name"):
        await append_to_notepad(workspace, "p", "diary", "x")
    # Verify no delete/edit API exists (append-only contract)
    import app.core.notepad as n

    assert not hasattr(n, "delete_notepad")
    assert not hasattr(n, "edit_notepad")


# ---------------------------------------------------------------------------
# Test 4: Todo-enforcer accepts valid snapshot
# ---------------------------------------------------------------------------


async def test_validate_boulder_snapshot_accepts_valid():
    validate_boulder_snapshot(
        {
            "todos": [
                {"status": "completed", "title": "a", "completion_note": "done"},
                {"status": "in_progress", "title": "b"},
                {"status": "pending", "title": "c"},
                {"status": "cancelled", "title": "d"},
            ]
        }
    )


# ---------------------------------------------------------------------------
# Test 5: Todo-enforcer rejects completed without completion_note
# ---------------------------------------------------------------------------


async def test_completed_todo_without_note_rejected():
    with pytest.raises(TodoEnforcerError, match="completion_note"):
        validate_boulder_snapshot({"todos": [{"status": "completed", "title": "x"}]})
    with pytest.raises(TodoEnforcerError, match="completion_note"):
        validate_boulder_snapshot({"todos": [{"status": "completed", "title": "x", "completion_note": ""}]})


# ---------------------------------------------------------------------------
# Test 6: Todo-enforcer rejects multiple in_progress
# ---------------------------------------------------------------------------


async def test_multiple_in_progress_rejected():
    with pytest.raises(TodoEnforcerError, match="in_progress"):
        validate_boulder_snapshot(
            {
                "todos": [
                    {"status": "in_progress", "title": "a"},
                    {"status": "in_progress", "title": "b"},
                ]
            }
        )


# ---------------------------------------------------------------------------
# Test 7: Supervisor updates metrics on checkpoint
# ---------------------------------------------------------------------------


async def test_checkpoint_updates_metrics(
    wired_factory,  # noqa: ARG001 — get_session_factory() must use test loop
    session: AsyncSession,
    instance_factory,
    loop_state_factory,
):
    await supervisor.start()  # register harness.* handler (in test's loop)
    instance = await instance_factory()
    await loop_state_factory(instance)
    await session.commit()

    await emit(
        HARNESS_CHECKPOINT,
        actor_type="instance",
        actor_id=instance.id,
        resource_type="instance",
        resource_id=instance.id,
        payload={"token_estimate": 100},
        session=session,
    )
    await session.commit()

    metrics = supervisor.get_loop_status(instance.id)
    assert metrics["continuation_count"] == 1
    assert metrics["token_estimate"] == 100


# ---------------------------------------------------------------------------
# Test 8: max_continuations breaker trips
# ---------------------------------------------------------------------------


async def test_breaker_trips_on_max_continuations(
    wired_factory,  # noqa: ARG001 — get_session_factory() must use test loop
    session: AsyncSession,
    instance_factory,
    loop_state_factory,
):
    await supervisor.start()  # register harness.* handler (in test's loop)
    instance = await instance_factory()
    await loop_state_factory(instance, max_continuations=3)
    await session.commit()

    # The handler's `_check_breakers` uses `>=`: with max_continuations=3,
    # on the 3rd increment (continuation_count==3) it trips. After the trip,
    # ``_trip_breaker`` pops the registry entry, so emitting more would
    # re-create it. Emit exactly 3 checkpoints so the registry stays empty
    # after the trip and the assertion below holds.
    for _ in range(3):
        await emit(
            HARNESS_CHECKPOINT,
            actor_type="instance",
            actor_id=instance.id,
            resource_type="instance",
            resource_id=instance.id,
            payload={"token_estimate": 0},
            session=session,
        )
        await session.commit()

    result = await session.execute(
        select(Event).where(
            Event.type == HARNESS_BREAKER_TRIPPED,
            Event.resource_id == instance.id,
        )
    )
    trip_events = list(result.scalars().all())
    assert len(trip_events) >= 1
    assert trip_events[0].payload["reason"] == "max_continuations"
    # Registry entry removed after trip
    assert instance.id not in supervisor._registry


# ---------------------------------------------------------------------------
# Test 9: idle_timeout breaker trips (use continuation handler)
# ---------------------------------------------------------------------------


async def test_breaker_trips_on_idle_timeout(
    wired_factory,  # noqa: ARG001 — get_session_factory() must use test loop
    session: AsyncSession,
    instance_factory,
    loop_state_factory,
):
    from app.core.queue import InMemoryTaskQueue

    instance = await instance_factory()
    old = datetime.now(timezone.utc).replace(year=2020, month=1, day=1)
    state = await loop_state_factory(
        instance,
        idle_timeout_seconds=1,
        last_checkpoint_at=old,
        loop_status="running",
    )
    # Wall-clock and continuation caps high so ONLY idle_timeout can trip
    state.max_continuations = 999999
    state.max_wall_clock_seconds = 999999
    state.max_token_estimate = 999999999
    await session.commit()

    # Pre-populate the registry with stale last_checkpoint_at so
    # `_check_breakers` finds a registry entry (the _on_harness_event
    # path that would normally populate this is bypassed here).
    supervisor._registry[instance.id] = InstanceLoopMetrics(
        continuation_count=0,
        token_estimate=0,
        wall_clock_started=datetime.now(timezone.utc),
        last_checkpoint_at=old,
    )

    queue = InMemoryTaskQueue()
    queue.register_task("idle_check", idle_check_handler)
    await queue.start()
    try:
        await idle_check_handler({"task_queue": queue})
        await asyncio.sleep(0)
    finally:
        await queue.stop()

    result = await session.execute(
        select(Event).where(
            Event.type == HARNESS_BREAKER_TRIPPED,
            Event.resource_id == instance.id,
        )
    )
    events = list(result.scalars().all())
    assert any(e.payload.get("reason") == "idle_timeout" for e in events), (
        f"Expected idle_timeout trip; got reasons: {[e.payload.get('reason') for e in events]}"
    )


# ---------------------------------------------------------------------------
# Test 10: /interrupt changes status
# ---------------------------------------------------------------------------


async def test_interrupt_changes_status(
    client: TestClient,
    session: AsyncSession,
    auth_token: str,
    auth_user_id: str,
    loop_state_factory,
):
    instance_office = _setup_office_and_membership(
        client,
        auth_token,
        auth_user_id,
        office_name="Interrupt Office",
        office_slug="interrupt-office",
    )
    employee_id = _create_employee(
        client,
        auth_token,
        "interrupt-emp",
        "Interrupt Employee",
    )
    h = {"Authorization": f"Bearer {auth_token}"}
    resp = client.post(
        "/api/v1/instances",
        headers=h,
        json={"employee_id": employee_id, "office_id": instance_office},
    )
    assert resp.status_code == 201
    inst_id = resp.json()["id"]

    # Fetch the Instance via DB to use loop_state_factory
    result = await session.execute(select(Instance).where(Instance.id == inst_id))
    inst_obj = result.scalars().first()
    assert inst_obj is not None

    await loop_state_factory(inst_obj, loop_status="running")
    await session.commit()

    response = client.post(
        f"/api/v1/instances/{inst_id}/interrupt",
        headers=h,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["loop_status"] == "interrupted"


# ---------------------------------------------------------------------------
# Test 11: /pause then /resume
# ---------------------------------------------------------------------------


async def test_pause_and_resume(
    client: TestClient,
    session: AsyncSession,
    auth_token: str,
    auth_user_id: str,
    loop_state_factory,
):
    instance_office = _setup_office_and_membership(
        client,
        auth_token,
        auth_user_id,
        office_name="Pause Office",
        office_slug="pause-office",
    )
    employee_id = _create_employee(
        client,
        auth_token,
        "pause-emp",
        "Pause Employee",
    )
    h = {"Authorization": f"Bearer {auth_token}"}
    resp = client.post(
        "/api/v1/instances",
        headers=h,
        json={"employee_id": employee_id, "office_id": instance_office},
    )
    assert resp.status_code == 201
    inst_id = resp.json()["id"]

    result = await session.execute(select(Instance).where(Instance.id == inst_id))
    inst_obj = result.scalars().first()
    assert inst_obj is not None

    await loop_state_factory(inst_obj, loop_status="running")
    await session.commit()

    r1 = client.post(f"/api/v1/instances/{inst_id}/pause", headers=h)
    assert r1.status_code == 200
    assert r1.json()["loop_status"] == "paused"

    r2 = client.post(f"/api/v1/instances/{inst_id}/resume", headers=h)
    assert r2.status_code == 200
    assert r2.json()["loop_status"] == "running"


# ---------------------------------------------------------------------------
# Test 12: GET /status returns merged state + metrics
# ---------------------------------------------------------------------------


async def test_status_endpoint(
    client: TestClient,
    session: AsyncSession,
    auth_token: str,
    auth_user_id: str,
    loop_state_factory,
):
    instance_office = _setup_office_and_membership(
        client,
        auth_token,
        auth_user_id,
        office_name="Status Office",
        office_slug="status-office",
    )
    employee_id = _create_employee(
        client,
        auth_token,
        "status-emp",
        "Status Employee",
    )
    h = {"Authorization": f"Bearer {auth_token}"}
    resp = client.post(
        "/api/v1/instances",
        headers=h,
        json={"employee_id": employee_id, "office_id": instance_office},
    )
    assert resp.status_code == 201
    inst_id = resp.json()["id"]

    result = await session.execute(select(Instance).where(Instance.id == inst_id))
    inst_obj = result.scalars().first()
    assert inst_obj is not None

    await loop_state_factory(inst_obj, loop_status="running")
    await session.commit()

    response = client.get(f"/api/v1/instances/{inst_id}/status", headers=h)
    assert response.status_code == 200
    body = response.json()
    assert body["instance_id"] == inst_id
    assert body["loop_status"] == "running"
    assert "breaker_config" in body
    assert body["breaker_config"]["max_continuations"] == 50  # default


# ---------------------------------------------------------------------------
# Test 13: POST /snapshot captures boulder_snapshot
# ---------------------------------------------------------------------------


async def test_capture_snapshot(
    client: TestClient,
    session: AsyncSession,
    auth_token: str,
    auth_user_id: str,
    loop_state_factory,
):
    instance_office = _setup_office_and_membership(
        client,
        auth_token,
        auth_user_id,
        office_name="Snapshot Office",
        office_slug="snapshot-office",
    )
    employee_id = _create_employee(
        client,
        auth_token,
        "snapshot-emp",
        "Snapshot Employee",
    )
    h = {"Authorization": f"Bearer {auth_token}"}
    resp = client.post(
        "/api/v1/instances",
        headers=h,
        json={"employee_id": employee_id, "office_id": instance_office},
    )
    assert resp.status_code == 201
    inst_id = resp.json()["id"]

    result = await session.execute(select(Instance).where(Instance.id == inst_id))
    inst_obj = result.scalars().first()
    assert inst_obj is not None

    valid_snapshot = {"todos": [{"status": "in_progress", "title": "x"}]}
    await loop_state_factory(
        inst_obj,
        boulder_snapshot=valid_snapshot,
    )
    await session.commit()

    response = client.post(f"/api/v1/instances/{inst_id}/snapshot", headers=h)
    assert response.status_code == 200
    body = response.json()
    assert body["boulder_snapshot"]["todos"][0]["status"] == "in_progress"


# ---------------------------------------------------------------------------
# Test 14: agent loop emits loop_started, checkpoints, loop_stopped
# ---------------------------------------------------------------------------


async def test_agent_loop_runs_checkpoints(
    wired_factory,  # noqa: ARG001 — get_session_factory() must use test loop
    session: AsyncSession,
    instance_factory,
    loop_state_factory,
):
    from app.agent_runtime import run_agent_loop

    instance = await instance_factory()
    instance.workspace_path = tempfile.mkdtemp(prefix="agent-test-")
    await session.commit()
    await loop_state_factory(instance, loop_status="running")
    await session.commit()

    await run_agent_loop(instance.id)

    for expected in [HARNESS_LOOP_STARTED, HARNESS_LOOP_STOPPED]:
        result = await session.execute(
            select(Event).where(
                Event.type == expected,
                Event.resource_id == instance.id,
            )
        )
        assert result.scalars().first() is not None, f"Missing {expected}"

    result = await session.execute(
        select(Event).where(
            Event.type == HARNESS_CHECKPOINT,
            Event.resource_id == instance.id,
        )
    )
    checkpoints = list(result.scalars().all())
    assert len(checkpoints) >= 1


# ---------------------------------------------------------------------------
# Test 15: agent loop stops on interrupt (loop_status change)
# ---------------------------------------------------------------------------


async def test_agent_loop_stops_on_interrupt(
    wired_factory,  # noqa: ARG001 — get_session_factory() must use test loop
    session: AsyncSession,
    instance_factory,
    loop_state_factory,
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

    result = await session.execute(
        select(Event).where(
            Event.type == HARNESS_CHECKPOINT,
            Event.resource_id == instance.id,
        )
    )
    checkpoints = list(result.scalars().all())
    assert len(checkpoints) < 10, f"Expected early stop, but {len(checkpoints)} checkpoints were emitted"


# ---------------------------------------------------------------------------
# Test 16: idle_check emits continuation_injected for stale running instance
# ---------------------------------------------------------------------------


async def test_continuation_injected_on_timeout(
    wired_factory,  # noqa: ARG001 — get_session_factory() must use test loop
    session: AsyncSession,
    instance_factory,
    loop_state_factory,
):
    from app.core.queue import InMemoryTaskQueue

    instance = await instance_factory()
    old = datetime.now(timezone.utc).replace(year=2020)
    state = await loop_state_factory(
        instance,
        loop_status="running",
        last_checkpoint_at=old,
        idle_timeout_seconds=1,
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

    result = await session.execute(
        select(Event).where(
            Event.type == HARNESS_CONTINUATION_INJECTED,
            Event.resource_id == instance.id,
        )
    )
    cont = result.scalars().first()
    assert cont is not None, "Expected continuation_injected event"
    assert cont.payload["plan_ref"] is None  # current_plan_ref was None


# ---------------------------------------------------------------------------
# Test 17: P5 route_turn bare-cmd drop regression
# ---------------------------------------------------------------------------


async def test_p5_route_turn_unaffected_by_p8_changes(
    session: AsyncSession,
    office_factory,
):
    """Verify P8 control-command branch does NOT break P5's bare-cmd drop semantics.

    Per M7 review: directive_router should silently drop a bare /interrupt
    with no @target — matching P5's pre-existing bare-cmd contract. The P8
    control-command branch must NOT alter this contract.
    """
    from app.core.directive_router import route_turn

    # Build user + office + membership directly (skip auth flow — we test
    # the routing engine, not the HTTP layer).
    user = User(
        username=f"p5_user_{uuid.uuid4().hex[:6]}",
        email=f"p5_user_{uuid.uuid4().hex[:6]}@test.com",
        password_hash="x",
    )
    session.add(user)
    await session.flush()

    office = await office_factory()
    membership = Membership(
        user_id=user.id,
        office_id=office.id,
        hex_q=0,
        hex_r=0,
        role=MembershipRole.editor.value,
    )
    session.add(membership)
    await session.flush()

    # Bare /interrupt with no @target — must be silently dropped
    results = await route_turn(
        session=session,
        raw_text="/interrupt",
        office_id=office.id,
        from_user_id=user.id,
    )

    # P5 contract: bare cmd returns list with all DirectiveResult.results empty.
    assert isinstance(results, list)
    assert len(results) >= 1
    for r in results:
        assert r.results == [], f"Bare /interrupt must not produce results; got {r.results!r}"
        assert r.target_employee is None
        assert r.cmd == "/interrupt"
