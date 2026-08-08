"""Pytest fixtures for the Cocoa backend test suite.

Isolation model: a session-scoped template database is built once via Alembic
migrations. Every DB-touching test clones a private database from that
template (`CREATE DATABASE ... TEMPLATE ...`), runs against it, and drops it
afterwards. Tests can never see each other's data, and `cocoa_dev` (the
Alembic-managed development schema) is never touched by the test suite.
"""

import os
import subprocess
import tempfile
import uuid

import asyncpg
import pytest
import pytest_asyncio
from _pytest.monkeypatch import MonkeyPatch
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

_ADMIN_DSN = "postgresql://postgres:postgres@127.0.0.1:5432/postgres"
_TEMPLATE_DB = "cocoa_test_template"
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pytest_configure(config: pytest.Config) -> None:
    """Point FORNIX_ROOT at a session tmp dir before any app import.

    ``app.core.config`` instantiates ``Settings()`` at module import time, so
    the env var must be set before test modules (or the ``client`` fixture)
    import the app. This keeps every FornixFile write out of the real
    ``/var/cocoa/workspaces`` mount.
    """
    if "FORNIX_ROOT" not in os.environ:
        os.environ["FORNIX_ROOT"] = tempfile.mkdtemp(prefix="cocoa_fornix_root_")


def _url(db: str) -> str:
    return f"postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/{db}"


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
        from collections import defaultdict as _dd

        from app.main import app as _app
        _stack = _app.middleware_stack
        while _stack is not None:
            if hasattr(_stack, "_counters") and isinstance(getattr(_stack, "_counters", None), _dd):
                _stack._counters.clear()
                break
            _stack = getattr(_stack, "app", None)

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
async def namespace_factory(session: AsyncSession):
    """Ensure a default Organization+Namespace exist; return Namespace."""

    async def _make(**overrides):

        from sqlalchemy import select

        from app.models.organization import Namespace, Organization

        org = (
            await session.execute(
                select(Organization).where(
                    Organization.slug == "default",
                    Organization.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if org is None:
            org = Organization(slug="default", name="Default World")
            session.add(org)
            await session.flush()

        slug = overrides.pop("slug", "default")
        ns = (
            await session.execute(
                select(Namespace).where(
                    Namespace.org_id == org.id,
                    Namespace.slug == slug,
                    Namespace.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if ns is None:
            ns = Namespace(
                org_id=org.id,
                slug=slug,
                name=overrides.pop("name", "Default Scenario"),
                description=overrides.pop("description", None),
                tags=overrides.pop("tags", None),
            )
            session.add(ns)
            await session.flush()
        return ns

    return _make


@pytest_asyncio.fixture
async def workspace_factory(session: AsyncSession, namespace_factory):
    """Return an async factory of :class:`Workspace` rows bound to *session*."""

    async def _make(**overrides):
        import uuid as _uuid

        from app.models.workspace import Workspace

        if "namespace_id" not in overrides:
            ns = await namespace_factory()
            overrides["namespace_id"] = ns.id

        defaults = {
            "name": overrides.pop("name", "Test Workspace"),
            "slug": overrides.pop("slug", f"test-workspace-{_uuid.uuid4().hex[:8]}"),
        }
        defaults.update(overrides)
        workspace = Workspace(**defaults)
        session.add(workspace)
        await session.flush()
        return workspace

    return _make


@pytest_asyncio.fixture
async def entity_factory(session: AsyncSession, namespace_factory):
    """Return an async factory of :class:`Entity` rows bound to *session*."""

    async def _make(**overrides):
        import uuid as _uuid

        from app.models.entity import Entity

        if "namespace_id" not in overrides:
            ns = await namespace_factory()
            overrides["namespace_id"] = ns.id

        defaults = {
            "name": overrides.pop("name", "Test Entity"),
            "slug": overrides.pop("slug", f"test-emp-{_uuid.uuid4().hex[:8]}"),
        }
        defaults.update(overrides)
        emp = Entity(**defaults)
        session.add(emp)
        await session.flush()
        return emp

    return _make


@pytest_asyncio.fixture
async def instance_factory(session: AsyncSession, entity_factory, workspace_factory):
    """Return an async factory of :class:`Instance` rows bound to *session*."""

    async def _make(**overrides):
        import uuid as _uuid

        from app.models.instance import Instance, InstanceStatus

        if "entity_id" not in overrides:
            emp = await entity_factory()
            overrides["entity_id"] = emp.id
        if "workspace_id" not in overrides:
            workspace = await workspace_factory()
            overrides["workspace_id"] = workspace.id
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
async def create_org_bundle(session: AsyncSession):
    """v4.0 M7: Org + OrgContract + atom grants (+ optional role-less Membership).

    Replaces the old "insert editor-role Membership" fixture pattern: tests
    that exercise permission-gated endpoints grant contract atoms instead.
    """

    async def _make(
        user_id: str | None = None,
        *,
        atoms: tuple[str, ...] = (
            "can_view_workspace",
            "can_edit_workspace",
            "can_operate_workspace",
            "can_manage_workspace",
        ),
        workspace=None,
        namespace=None,
        organization=None,
        with_membership: bool = False,
        posx: int = 0,
        posy: int = 0,
    ):
        from types import SimpleNamespace

        from sqlalchemy import select

        from app.core.gene_atoms import ensure_atom_genes
        from app.core.org_contract import ensure_org_contract, grant_atoms
        from app.models.organization import Namespace, Organization
        from app.models.workspace import Membership

        org = organization
        ns = namespace
        if org is None:
            if ns is not None:
                org = await session.get(Organization, ns.org_id)
            elif workspace is not None:
                ns = await session.get(Namespace, workspace.namespace_id)
                org = await session.get(Organization, ns.org_id)
            else:
                org = (
                    await session.execute(
                        select(Organization).where(
                            Organization.slug == "default",
                            Organization.deleted_at.is_(None),
                        )
                    )
                ).scalar_one_or_none()
                if org is None:
                    org = Organization(slug="default", name="Default World")
                    session.add(org)
                    await session.flush()
        if ns is None and workspace is not None:
            ns = await session.get(Namespace, workspace.namespace_id)

        await ensure_atom_genes(session)
        contract = None
        if user_id is not None and org is not None:
            contract = await ensure_org_contract(
                session, organization_id=org.id, user_id=user_id
            )
            await grant_atoms(session, contract.id, atoms)

        membership = None
        if with_membership and user_id is not None and workspace is not None:
            membership = Membership(
                workspace_id=workspace.id,
                user_id=user_id,
                posx=posx,
                posy=posy,
            )
            session.add(membership)
            await session.flush()

        # Commit so grants are visible to the API client's separate session.
        await session.commit()

        return SimpleNamespace(
            org=org,
            namespace=ns,
            workspace=workspace,
            contract=contract,
            membership=membership,
        )

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
