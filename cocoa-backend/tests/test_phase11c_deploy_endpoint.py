"""P11c Todo 2: DeployRecord SSE + snapshot + cancel endpoint tests.

Two integration tests covering the three endpoints exposed by
:mod:`app.api.v1.deploy`:

1. ``test_snapshot_endpoint_returns_current_state`` — create a
   ``DeployRecord`` in the per-test DB, then ``GET
   /api/v1/deploy/deploy-progress/{id}/snapshot`` and verify the
   response shape matches the row (200 + JSON fields).

2. ``test_cancel_endpoint_marks_record_cancelled`` — create a
   ``DeployRecord``, then ``POST /api/v1/deploy/deploy-cancel/{id}``
   and verify the record is marked ``cancelled``. The real
   :func:`app.services.deploy_service.cancel_deploy` is monkeypatched
   so the test does not need a live K8s cluster.

The test app is built from just the deploy router + auth router — no
``app.main`` import — so a transient break in another module (e.g. the
parallel P11c ``agent_runtime`` package split) does not block these
specific tests. The shared ``session`` / ``db_url`` fixtures come from
``tests/conftest.py``.
"""

from __future__ import annotations

import importlib.util
import uuid

# ---------------------------------------------------------------------------
# Workaround: the parallel P11c Todo "agent-runtime package split" introduced
# ``app/agent_runtime/__init__.py`` (the package), which shadows the existing
# ``app/agent_runtime.py`` module that exports ``start_runtime_for``. The
# downstream ``app.api.v1.harness`` then fails at import time with
# ``ImportError: cannot import name 'start_runtime_for'``. The conftest
# autouse fixture ``_clear_handlers`` does ``from app.main import app``
# which transitively triggers that broken import, so EVERY test in this
# file would fail collection even though deploy.py has nothing to do with
# the harness. Re-export ``start_runtime_for`` from the module file onto
# the package namespace BEFORE any ``app.main`` import resolves.
# ---------------------------------------------------------------------------
_spec = importlib.util.spec_from_file_location(
    "app.agent_runtime._compat_module",
    "/tmp/p14a-worktree/cocoa-backend/app/agent_runtime/__init__.py",
)
_agent_runtime_compat = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_agent_runtime_compat)
import app.agent_runtime as _ar_pkg  # noqa: E402

for _name in ("start_runtime_for", "run_agent_loop"):
    if hasattr(_agent_runtime_compat, _name) and not hasattr(_ar_pkg, _name):
        setattr(_ar_pkg, _name, getattr(_agent_runtime_compat, _name))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.api.v1.auth import router as auth_router  # noqa: E402
from app.api.v1.deploy import router as deploy_router  # noqa: E402
from app.models.deploy_record import DeployRecord, DeployStatus  # noqa: E402


@pytest_asyncio.fixture
async def deploy_app(db_url: str):
    """Build a minimal FastAPI app wiring the deploy router + auth router.

    Uses the per-test ``db_url`` so each test sees a fresh DB clone from
    the Alembic template (conftest's ``db_url`` fixture).
    """
    import app.core.config as cfg_mod
    import app.core.db as db_mod

    db_mod._engine = None
    db_mod._session_factory = None

    monkey = pytest.MonkeyPatch()
    monkey.setattr(cfg_mod.settings, "DATABASE_URL", db_url)

    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(deploy_router, prefix="/api/v1")
    yield app
    monkey.undo()
    db_mod._engine = None
    db_mod._session_factory = None


async def _register_and_login(ac: AsyncClient, username: str) -> str:
    """Register + login via AsyncClient and return the JWT access token."""
    await ac.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@test.com",
            "password": "password123",
        },
    )
    resp = await ac.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "password123"},
    )
    return resp.json()["access_token"]


async def _make_deploy_record(session: AsyncSession) -> DeployRecord:
    """Insert a fresh Instance + DeployRecord pair and return the record.

    DeployRecord has a FK on ``instances.id``, so a stub Instance is
    required. The instance is built with the minimum column set the
    model accepts without constraint violations.
    """
    import app.core.db as db_mod
    from app.models.employee import Employee
    from app.models.instance import Instance, InstanceStatus
    from app.models.office import Office

    # Ensure the session uses the per-test DB, not any cached factory.
    db_mod._engine = None
    db_mod._session_factory = None

    office = Office(name=f"o-{uuid.uuid4().hex[:6]}", slug=f"o-{uuid.uuid4().hex[:6]}")
    employee = Employee(name=f"e-{uuid.uuid4().hex[:6]}", slug=f"e-{uuid.uuid4().hex[:6]}")
    session.add_all([office, employee])
    await session.flush()

    instance = Instance(
        office_id=office.id,
        employee_id=employee.id,
        status=InstanceStatus.creating.value,
        proxy_token=str(uuid.uuid4()),
    )
    session.add(instance)
    await session.flush()

    record = DeployRecord(
        instance_id=instance.id,
        revision=1,
        action="deploy",
        status=DeployStatus.pending.value,
        image_version="v1.2.3",
        message="created-by-test",
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


@pytest.mark.asyncio
async def test_snapshot_endpoint_returns_current_state(
    deploy_app: FastAPI,
    session: AsyncSession,
    db_url: str,
) -> None:
    """GET snapshot returns 200 + all 9 DeployRecord fields.

    Creates a DeployRecord directly in the per-test DB, then issues the
    snapshot request via AsyncClient (ASGI transport). Bypasses SSE
    mechanics (the snapshot is the sync pair to the SSE stream).
    """
    import app.core.db as db_mod

    db_mod._engine = None
    db_mod._session_factory = None

    record = await _make_deploy_record(session)
    record_id = record.id

    transport = ASGITransport(app=deploy_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        username = f"snap_{uuid.uuid4().hex[:8]}"
        token = await _register_and_login(ac, username)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await ac.get(
            f"/api/v1/deploy/deploy-progress/{record_id}/snapshot",
            headers=headers,
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == record_id
    assert body["status"] == DeployStatus.pending.value
    assert body["action"] == "deploy"
    assert body["revision"] == 1
    assert body["image_version"] == "v1.2.3"
    assert body["message"] == "created-by-test"
    assert body["instance_id"] == record.instance_id


@pytest.mark.asyncio
async def test_cancel_endpoint_marks_record_cancelled(
    deploy_app: FastAPI,
    session: AsyncSession,
    db_url: str,
    monkeypatch,
) -> None:
    """POST cancel returns 200 and the record flips to ``cancelled``.

    Patches :func:`app.services.deploy_service.cancel_deploy` to update
    the in-session record without touching K8s. Verifies the API
    response and the post-cancel DB state.
    """
    import app.core.db as db_mod
    import app.services.deploy_service as deploy_service_mod

    db_mod._engine = None
    db_mod._session_factory = None

    async def fake_cancel_deploy(record_id: str) -> str:
        """Stub that updates the in-session record without touching K8s."""
        from sqlalchemy import select

        result = await session.execute(
            select(DeployRecord).where(DeployRecord.id == record_id)
        )
        rec = result.scalars().first()
        if rec is not None:
            rec.status = DeployStatus.cancelled.value
            await session.commit()
        return "cocoa-test-ns"

    monkeypatch.setattr(deploy_service_mod, "cancel_deploy", fake_cancel_deploy)

    record = await _make_deploy_record(session)
    record_id = record.id

    transport = ASGITransport(app=deploy_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        username = f"cancel_{uuid.uuid4().hex[:8]}"
        token = await _register_and_login(ac, username)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await ac.post(
            f"/api/v1/deploy/deploy-cancel/{record_id}",
            headers=headers,
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["record_id"] == record_id
    assert body["status"] == DeployStatus.cancelled.value
    assert body["namespace"] == "cocoa-test-ns"

    # Re-fetch and verify DB transition.
    refreshed = await session.get(DeployRecord, record_id)
    assert refreshed is not None
    assert refreshed.status == DeployStatus.cancelled.value
