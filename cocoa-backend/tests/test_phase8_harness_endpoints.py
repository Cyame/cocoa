"""P8 control-command endpoint tests.

Tests for the 5 P8 control endpoints (interrupt / pause / resume /
status / snapshot) living in :mod:`app.api.v1.harness`, plus the P5
route-turn regression that must not be affected by the P8 changes.

Shared fixtures (``_clear_handlers`` autouse + ``loop_state_factory``)
live in ``tests/conftest.py``; auth fixtures are local to this module.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.models.instance import Instance
from app.models.workspace import Membership, MembershipRole
from app.models.user import User


@pytest.fixture(autouse=True)
def _raise_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.middleware.rate_limit.MAX_REQUESTS_PER_WINDOW",
        100_000,
    )


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


async def _bootstrap_instance(
    client: TestClient,
    auth_token: str,
    auth_user_id: str,
    session: AsyncSession,
    *,
    workspace_name: str,
    workspace_slug: str,
    entity_slug: str,
    entity_name: str,
) -> tuple[Instance, dict]:
    """Create workspace + entity + instance via HTTP; return (Instance, headers).

    Note (P14b-onboard2): the workspace creator is auto-added as an owner
    Membership by ``POST /workspaces``, so we no longer manually issue a join
    after workspace creation (which would now return 409 Conflict).
    """
    h = {"Authorization": f"Bearer {auth_token}"}
    workspace = client.post(
        "/api/v1/workspaces",
        headers=h,
        json={"name": workspace_name, "slug": workspace_slug},
    ).json()
    entity_id = client.post(
        "/api/v1/entities",
        headers=h,
        json={"name": entity_name, "slug": entity_slug},
    ).json()["id"]
    resp = client.post(
        "/api/v1/instances",
        headers=h,
        json={"entity_id": entity_id, "workspace_id": workspace["id"]},
    )
    assert resp.status_code == 201
    inst_id = resp.json()["id"]
    result = await session.execute(select(Instance).where(Instance.id == inst_id))
    return result.scalars().first(), h


async def test_interrupt_changes_status(
    client: TestClient,
    session: AsyncSession,
    auth_token: str,
    auth_user_id: str,
    loop_state_factory,
):
    inst_obj, h = await _bootstrap_instance(
        client, auth_token, auth_user_id, session,
        workspace_name="Interrupt Workspace", workspace_slug="interrupt-workspace",
        entity_slug="interrupt-emp", entity_name="Interrupt Entity",
    )
    await loop_state_factory(inst_obj, loop_status="running")
    await session.commit()

    response = client.post(
        f"/api/v1/instances/{inst_obj.id}/interrupt", headers=h
    )
    assert response.status_code == 200
    assert response.json()["loop_status"] == "interrupted"


async def test_pause_and_resume(
    client: TestClient,
    session: AsyncSession,
    auth_token: str,
    auth_user_id: str,
    loop_state_factory,
):
    inst_obj, h = await _bootstrap_instance(
        client, auth_token, auth_user_id, session,
        workspace_name="Pause Workspace", workspace_slug="pause-workspace",
        entity_slug="pause-emp", entity_name="Pause Entity",
    )
    await loop_state_factory(inst_obj, loop_status="running")
    await session.commit()

    r1 = client.post(f"/api/v1/instances/{inst_obj.id}/pause", headers=h)
    assert r1.status_code == 200
    assert r1.json()["loop_status"] == "paused"
    r2 = client.post(f"/api/v1/instances/{inst_obj.id}/resume", headers=h)
    assert r2.status_code == 200
    assert r2.json()["loop_status"] == "running"


async def test_status_endpoint(
    client: TestClient,
    session: AsyncSession,
    auth_token: str,
    auth_user_id: str,
    loop_state_factory,
):
    inst_obj, h = await _bootstrap_instance(
        client, auth_token, auth_user_id, session,
        workspace_name="Status Workspace", workspace_slug="status-workspace",
        entity_slug="status-emp", entity_name="Status Entity",
    )
    await loop_state_factory(inst_obj, loop_status="running")
    await session.commit()

    response = client.get(f"/api/v1/instances/{inst_obj.id}/status", headers=h)
    assert response.status_code == 200
    body = response.json()
    assert body["instance_id"] == inst_obj.id
    assert body["loop_status"] == "running"
    assert body["breaker_config"]["max_continuations"] == 50  # default


async def test_capture_snapshot(
    client: TestClient,
    session: AsyncSession,
    auth_token: str,
    auth_user_id: str,
    loop_state_factory,
):
    inst_obj, h = await _bootstrap_instance(
        client, auth_token, auth_user_id, session,
        workspace_name="Snapshot Workspace", workspace_slug="snapshot-workspace",
        entity_slug="snapshot-emp", entity_name="Snapshot Entity",
    )
    valid_snapshot = {"todos": [{"status": "in_progress", "title": "x"}]}
    await loop_state_factory(inst_obj, boulder_snapshot=valid_snapshot)
    await session.commit()

    response = client.post(f"/api/v1/instances/{inst_obj.id}/snapshot", headers=h)
    assert response.status_code == 200
    body = response.json()
    assert body["boulder_snapshot"]["todos"][0]["status"] == "in_progress"


async def test_p5_route_turn_unaffected_by_p8_changes(
    session: AsyncSession,
    workspace_factory,
):
    """Verify P8 control-command branch does NOT break P5's bare-cmd drop.

    Per M7 review: directive_router should silently drop a bare /interrupt
    with no @target — matching P5's pre-existing bare-cmd contract.
    """
    from app.core.directive_router import route_turn

    user = User(
        username=f"p5_user_{uuid.uuid4().hex[:6]}",
        email=f"p5_user_{uuid.uuid4().hex[:6]}@test.com",
        password_hash="x",
    )
    session.add(user)
    await session.flush()

    workspace = await workspace_factory()
    membership = Membership(
        user_id=user.id,
        workspace_id=workspace.id,
        posx=0,
        posy=0,
        role=MembershipRole.editor.value,
    )
    session.add(membership)
    await session.flush()

    # Bare /interrupt with no @target — must be silently dropped.
    results = await route_turn(
        session=session,
        raw_text="/interrupt",
        workspace_id=workspace.id,
        from_user_id=user.id,
    )

    # P5 contract: bare cmd returns list with all DirectiveResult.results empty.
    assert isinstance(results, list)
    assert len(results) >= 1
    for r in results:
        assert r.results == []
        assert r.target_entity is None
        assert r.cmd == "/interrupt"
