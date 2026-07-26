"""Pytest fixtures for the Cocoa backend test suite.

Isolation model: a session-scoped template database is built once via Alembic
migrations. Every DB-touching test clones a private database from that
template (`CREATE DATABASE ... TEMPLATE ...`), runs against it, and drops it
afterwards. Tests can never see each other's data, and `cocoa_dev` (the
Alembic-managed development schema) is never touched by the test suite.
"""

import os
import subprocess
import uuid

import asyncpg
import pytest_asyncio
from _pytest.monkeypatch import MonkeyPatch
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

_ADMIN_DSN = "postgresql://postgres:postgres@localhost:5432/postgres"
_TEMPLATE_DB = "cocoa_test_template"
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _url(db: str) -> str:
    return f"postgresql+asyncpg://postgres:postgres@localhost:5432/{db}"


async def _exec_admin(sql: str) -> None:
    """Run a statement against the admin database (autocommit, no transaction)."""
    conn = await asyncpg.connect(_ADMIN_DSN)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def _template_db():
    """Build the migrated schema template once per test session."""
    await _exec_admin(f'DROP DATABASE IF EXISTS {_TEMPLATE_DB} WITH (FORCE)')
    await _exec_admin(f'CREATE DATABASE {_TEMPLATE_DB}')
    env = {**os.environ, "DATABASE_URL": _url(_TEMPLATE_DB)}
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=_BACKEND_DIR,
        env=env,
        check=True,
        capture_output=True,
    )
    yield _TEMPLATE_DB
    await _exec_admin(f'DROP DATABASE IF EXISTS {_TEMPLATE_DB} WITH (FORCE)')


@pytest_asyncio.fixture
async def db_url(_template_db):
    """A private database cloned from the migrated template, per test."""
    name = f"cocoa_test_{uuid.uuid4().hex[:12]}"
    await _exec_admin(f'CREATE DATABASE {name} TEMPLATE {_template_db}')
    yield _url(name)
    await _exec_admin(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)')


@pytest_asyncio.fixture
async def session(db_url):
    """Async ORM session bound to the test's private database."""
    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clear_handlers():
    """Reset global handler list + supervisor registry around every test.

    Critical per C4 review: without this, harness.* handlers pile up across
    tests, causing state from previous tests to leak (e.g., stale
    supervisor._registry entries, leftover event handlers, in-flight
    task queue singletons).
    """
    import app.core.activation as act_mod
    import app.core.events as ev_mod

    try:
        from app.core.harness_supervisor import supervisor
    except ImportError:
        supervisor = None

    def _reset() -> None:
        if supervisor is not None:
            supervisor._registry.clear()
            supervisor._runtime_tasks.clear()
        ev_mod._handlers.clear()
        act_mod._pending_daily_report = None
        act_mod._task_queue = None

    _reset()
    yield
    _reset()


@pytest_asyncio.fixture
async def loop_state_factory(session: AsyncSession):
    """Create an InstanceLoopState row tied to an existing Instance."""

    async def _make(instance, **overrides):
        from app.models.loop_state import InstanceLoopState, LoopStatus

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


@pytest_asyncio.fixture
async def office_factory(session: AsyncSession):
    """Return an async factory of :class:`Office` rows bound to *session*."""

    async def _make(**overrides):
        import uuid as _uuid

        from app.models.office import Office

        defaults = {
            "name": overrides.pop("name", "Test Office"),
            "slug": overrides.pop("slug", f"test-office-{_uuid.uuid4().hex[:8]}"),
        }
        defaults.update(overrides)
        office = Office(**defaults)
        session.add(office)
        await session.flush()
        return office

    return _make


@pytest_asyncio.fixture
async def employee_factory(session: AsyncSession):
    """Return an async factory of :class:`Employee` rows bound to *session*."""

    async def _make(**overrides):
        import uuid as _uuid

        from app.models.employee import Employee

        defaults = {
            "name": overrides.pop("name", "Test Employee"),
            "slug": overrides.pop("slug", f"test-emp-{_uuid.uuid4().hex[:8]}"),
        }
        defaults.update(overrides)
        emp = Employee(**defaults)
        session.add(emp)
        await session.flush()
        return emp

    return _make


@pytest_asyncio.fixture
async def instance_factory(session: AsyncSession, employee_factory, office_factory):
    """Return an async factory of :class:`Instance` rows bound to *session*."""

    async def _make(**overrides):
        import uuid as _uuid

        from app.models.instance import Instance, InstanceStatus

        if "employee_id" not in overrides:
            emp = await employee_factory()
            overrides["employee_id"] = emp.id
        if "office_id" not in overrides:
            office = await office_factory()
            overrides["office_id"] = office.id
        defaults = {
            "status": InstanceStatus.creating.value,
            "proxy_token": str(_uuid.uuid4()),
        }
        defaults.update(overrides)
        inst = Instance(**defaults)
        session.add(inst)
        await session.flush()
        return inst

    return _make


@pytest_asyncio.fixture
async def client(db_url: str):
    """TestClient wired to the per-test cloned database."""
    import app.core.db as db_mod
    from app.main import app

    monkeypatch = MonkeyPatch()
    monkeypatch.setattr("app.core.config.settings.DATABASE_URL", db_url)
    db_mod._engine = None
    db_mod._session_factory = None
    with TestClient(app) as tc:
        yield tc
    # P7.5: 清理事件 handler 全局列表，防止测试间跨污染
    import app.core.events as ev_mod
    ev_mod._handlers.clear()
    # P7.5-comprehensive-review: module-level `_pending_daily_report` would otherwise
    # prevent registration on subsequent queue instances (e.g., test lifespan re-entry).
    # Reset to None so the new queue always gets registered.
    import app.core.activation as act_mod
    act_mod._pending_daily_report = None
    act_mod._task_queue = None
    # P8 Supervisor 模块级单例清理（try/except 包裹，P8 后才存在）
    try:
        from app.core.harness_supervisor import supervisor
        supervisor._registry.clear()
    except ImportError:
        pass
    # Teardown: dispose engine if it was created (lifespan in P3 is stub, no DB — but for P3.5 compatibility)
    if db_mod._engine is not None:
        try:
            await db_mod._engine.dispose()
        except Exception:
            pass  # cross-loop disposal may fail; DROP DATABASE WITH (FORCE) is the backstop
    db_mod._engine = None
    db_mod._session_factory = None
    monkeypatch.undo()
