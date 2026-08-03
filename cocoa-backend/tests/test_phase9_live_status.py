"""Integration tests for the P9 live-status aggregation endpoint.

Phase-15f T4: also verifies that the phase-15f fields (``outdated`` and
``active_hash``) are correctly joined from the Instance/Entity tables.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.models.instance import Instance
from app.models.workspace import Membership
from app.models.user import User


@pytest.fixture
def phase9_auth_token(client: TestClient) -> str:
    """Register and login a throwaway user for one endpoint test."""
    client.post(
        "/api/v1/auth/register",
        json={
            "username": "phase9-live-status",
            "email": "phase9-live-status@test.com",
            "password": "password123",
        },
    )
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "phase9-live-status", "password": "password123"},
    )
    return response.json()["access_token"]


@pytest_asyncio.fixture
async def phase9_auth_user_id(
    phase9_auth_token: str,
    session: AsyncSession,
) -> str:
    """Return the authenticated user's database ID."""
    from sqlalchemy import select

    result = await session.execute(
        select(User).where(User.username == "phase9-live-status"),
    )
    user = result.scalar_one()
    return user.id


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_membership(
    session: AsyncSession,
    *,
    workspace_id: str,
    user_id: str | None = None,
    instance_id: str | None = None,
    posx: int,
    posy: int,
) -> Membership:
    """Insert one membership for endpoint fixture setup."""
    membership = Membership(
        workspace_id=workspace_id,
        user_id=user_id,
        instance_id=instance_id,
        posx=posx,
        posy=posy,
    )
    session.add(membership)
    await session.flush()
    return membership


@pytest.mark.asyncio
async def test_live_status_aggregates_user_and_instance_memberships(
    client: TestClient,
    phase9_auth_token: str,
    phase9_auth_user_id: str,
    session: AsyncSession,
    workspace_factory,
    instance_factory,
    loop_state_factory,
) -> None:
    """An authorized workspace returns user and running-instance glow items."""
    user_id = phase9_auth_user_id
    workspace = await workspace_factory()
    instance = await instance_factory(workspace_id=workspace.id)
    instance.status = "running"
    await _create_membership(
        session,
        workspace_id=workspace.id,
        user_id=user_id,
        posx=10,
        posy=20,
    )
    await _create_membership(
        session,
        workspace_id=workspace.id,
        instance_id=instance.id,
        posx=30,
        posy=40,
    )
    await loop_state_factory(instance, loop_status="running")
    await session.commit()

    response = client.get(
        f"/api/v1/workspaces/{workspace.id}/live-status",
        headers=_auth(phase9_auth_token),
    )

    assert response.status_code == 200
    items = {item["node_type"]: item for item in response.json()}
    assert items["user"]["glow"] == {"color": "#4f46e5", "intensity": "medium"}
    assert items["user"]["posx"] == 10
    assert items["user"]["mentionable"] is False
    # running + no active conversation → idle (yellow), not harness "running"
    assert items["instance"]["glow"] == {"color": "#eab308", "intensity": "medium"}
    assert items["instance"]["posy"] == 40
    assert items["instance"]["instance_status"] == "running"
    assert items["instance"]["display_status"] == "idle"
    assert items["instance"]["mentionable"] is True


@pytest.mark.asyncio
async def test_live_status_rejects_non_member_workspace(
    client: TestClient,
    phase9_auth_token: str,
    workspace_factory,
) -> None:
    """An authenticated user without workspace membership receives 403."""
    workspace = await workspace_factory()

    response = client.get(
        f"/api/v1/workspaces/{workspace.id}/live-status",
        headers=_auth(phase9_auth_token),
    )

    assert response.status_code == 403
    assert response.json()["error_code"] == "workspace.not_member"


@pytest.mark.asyncio
async def test_live_status_returns_empty_for_empty_workspace(
    client: TestClient,
    phase9_auth_token: str,
    workspace_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An workspace with no active memberships returns an empty list."""
    workspace = await workspace_factory()

    async def allow_workspace_role(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        "app.api.v1.workspace_live_status.require_workspace_role",
        allow_workspace_role,
    )
    response = client.get(
        f"/api/v1/workspaces/{workspace.id}/live-status",
        headers=_auth(phase9_auth_token),
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_live_status_uses_avatar_display_glow(
    client: TestClient,
    phase9_auth_token: str,
    phase9_auth_user_id: str,
    session: AsyncSession,
    workspace_factory,
    entity_factory,
) -> None:
    """Canvas glow follows product display status, not harness loop_status."""
    user_id = phase9_auth_user_id
    workspace = await workspace_factory()
    await _create_membership(
        session,
        workspace_id=workspace.id,
        user_id=user_id,
        posx=1,
        posy=2,
    )
    await session.commit()

    from app.models.instance import Instance

    entity = await entity_factory()
    instance = Instance(
        entity_id=entity.id,
        workspace_id=workspace.id,
        proxy_token="unused",
        status="pending",
    )
    session.add(instance)
    await session.flush()
    membership = await _create_membership(
        session,
        workspace_id=workspace.id,
        instance_id=instance.id,
        posx=3,
        posy=4,
    )
    await session.commit()

    response = client.get(
        f"/api/v1/workspaces/{workspace.id}/live-status",
        headers=_auth(phase9_auth_token),
    )

    assert response.status_code == 200
    instance_item = next(item for item in response.json() if item["membership_id"] == membership.id)
    assert instance_item["display_status"] == "stopped"
    assert instance_item["glow"] == {"color": "#94a3b8", "intensity": "weak"}


# ---------------------------------------------------------------------------
# Phase-15f T4: outdated-detection + active_hash fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_live_status_outdated_when_active_hash_is_null(
    client: TestClient,
    phase9_auth_token: str,
    phase9_auth_user_id: str,
    session: AsyncSession,
    workspace_factory,
    entity_factory,
) -> None:
    """An instance with no active_hash is reported as outdated (first-time spawn)."""
    user_id = phase9_auth_user_id
    workspace = await workspace_factory()
    emp = await entity_factory()
    emp.migration_hash = "a" * 64
    await session.flush()

    instance = Instance(
        entity_id=emp.id,
        workspace_id=workspace.id,
        proxy_token="unused",
        active_hash=None,
    )
    session.add(instance)
    await session.flush()

    await _create_membership(
        session, workspace_id=workspace.id, user_id=user_id, posx=1, posy=2,
    )
    instance_membership = await _create_membership(
        session, workspace_id=workspace.id, instance_id=instance.id, posx=3, posy=4,
    )
    await session.commit()

    response = client.get(
        f"/api/v1/workspaces/{workspace.id}/live-status",
        headers=_auth(phase9_auth_token),
    )
    assert response.status_code == 200
    instance_item = next(
        item for item in response.json()
        if item["membership_id"] == instance_membership.id
    )
    assert instance_item["outdated"] is True
    assert instance_item["active_hash"] is None


@pytest.mark.asyncio
async def test_live_status_outdated_when_hash_mismatch(
    client: TestClient,
    phase9_auth_token: str,
    phase9_auth_user_id: str,
    session: AsyncSession,
    workspace_factory,
    entity_factory,
) -> None:
    """An instance whose active_hash differs from Entity.migration_hash is outdated."""
    user_id = phase9_auth_user_id
    workspace = await workspace_factory()
    emp = await entity_factory()
    emp.migration_hash = "b" * 64
    await session.flush()

    instance = Instance(
        entity_id=emp.id,
        workspace_id=workspace.id,
        proxy_token="unused",
        active_hash="c" * 64,
    )
    session.add(instance)
    await session.flush()

    await _create_membership(
        session, workspace_id=workspace.id, user_id=user_id, posx=1, posy=2,
    )
    await _create_membership(
        session, workspace_id=workspace.id, instance_id=instance.id, posx=3, posy=4,
    )
    await session.commit()

    response = client.get(
        f"/api/v1/workspaces/{workspace.id}/live-status",
        headers=_auth(phase9_auth_token),
    )
    assert response.status_code == 200
    instance_item = next(
        item for item in response.json()
        if item["active_hash"] == "c" * 64
    )
    assert instance_item["outdated"] is True


@pytest.mark.asyncio
async def test_live_status_in_sync_when_hashes_match(
    client: TestClient,
    phase9_auth_token: str,
    phase9_auth_user_id: str,
    session: AsyncSession,
    workspace_factory,
    entity_factory,
) -> None:
    """An instance whose active_hash matches Entity.migration_hash is in-sync."""
    user_id = phase9_auth_user_id
    workspace = await workspace_factory()
    emp = await entity_factory()
    emp.migration_hash = "d" * 64
    await session.flush()

    instance = Instance(
        entity_id=emp.id,
        workspace_id=workspace.id,
        proxy_token="unused",
        active_hash="d" * 64,
    )
    session.add(instance)
    await session.flush()

    await _create_membership(
        session, workspace_id=workspace.id, user_id=user_id, posx=1, posy=2,
    )
    await _create_membership(
        session, workspace_id=workspace.id, instance_id=instance.id, posx=3, posy=4,
    )
    await session.commit()

    response = client.get(
        f"/api/v1/workspaces/{workspace.id}/live-status",
        headers=_auth(phase9_auth_token),
    )
    assert response.status_code == 200
    instance_item = next(
        item for item in response.json()
        if item["active_hash"] == "d" * 64
    )
    assert instance_item["outdated"] is False


@pytest.mark.asyncio
async def test_live_status_user_node_never_outdated(
    client: TestClient,
    phase9_auth_token: str,
    phase9_auth_user_id: str,
    session: AsyncSession,
    workspace_factory,
) -> None:
    """A user-membership node always reports outdated=False and active_hash=None."""
    user_id = phase9_auth_user_id
    workspace = await workspace_factory()
    await _create_membership(
        session, workspace_id=workspace.id, user_id=user_id, posx=1, posy=2,
    )
    await session.commit()

    response = client.get(
        f"/api/v1/workspaces/{workspace.id}/live-status",
        headers=_auth(phase9_auth_token),
    )
    assert response.status_code == 200
    user_items = [i for i in response.json() if i["node_type"] == "user"]
    assert user_items
    for item in user_items:
        assert item["outdated"] is False
        assert item["active_hash"] is None
