"""Integration tests for the P9 live-status aggregation endpoint."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.models.office import Membership
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
    office_id: str,
    user_id: str | None = None,
    instance_id: str | None = None,
    posx: int,
    posy: int,
) -> Membership:
    """Insert one membership for endpoint fixture setup."""
    membership = Membership(
        office_id=office_id,
        user_id=user_id,
        instance_id=instance_id,
        posx=posx,
        posy=posy,
        role="owner" if user_id is not None else "viewer",
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
    office_factory,
    instance_factory,
    loop_state_factory,
) -> None:
    """An authorized office returns user and running-instance glow items."""
    user_id = phase9_auth_user_id
    office = await office_factory()
    instance = await instance_factory(office_id=office.id)
    await _create_membership(
        session,
        office_id=office.id,
        user_id=user_id,
        posx=10,
        posy=20,
    )
    await _create_membership(
        session,
        office_id=office.id,
        instance_id=instance.id,
        posx=30,
        posy=40,
    )
    await loop_state_factory(instance, loop_status="running")
    await session.commit()

    response = client.get(
        f"/api/v1/offices/{office.id}/live-status",
        headers=_auth(phase9_auth_token),
    )

    assert response.status_code == 200
    items = {item["node_type"]: item for item in response.json()}
    assert items["user"]["glow"] == {"color": "#4f46e5", "intensity": "medium"}
    assert items["user"]["posx"] == 10
    assert items["instance"]["glow"] == {"color": "#10b981", "intensity": "strong"}
    assert items["instance"]["posy"] == 40


@pytest.mark.asyncio
async def test_live_status_rejects_non_member_office(
    client: TestClient,
    phase9_auth_token: str,
    office_factory,
) -> None:
    """An authenticated user without office membership receives 403."""
    office = await office_factory()

    response = client.get(
        f"/api/v1/offices/{office.id}/live-status",
        headers=_auth(phase9_auth_token),
    )

    assert response.status_code == 403
    assert response.json()["error_code"] == "office.not_member"


@pytest.mark.asyncio
async def test_live_status_returns_empty_for_empty_office(
    client: TestClient,
    phase9_auth_token: str,
    office_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An office with no active memberships returns an empty list."""
    office = await office_factory()

    async def allow_office_role(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        "app.api.v1.office_live_status.require_office_role",
        allow_office_role,
    )
    response = client.get(
        f"/api/v1/offices/{office.id}/live-status",
        headers=_auth(phase9_auth_token),
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_live_status_uses_static_glow_without_loop_state(
    client: TestClient,
    phase9_auth_token: str,
    phase9_auth_user_id: str,
    session: AsyncSession,
    office_factory,
    employee_factory,
) -> None:
    """An instance membership without loop state uses static glow."""
    user_id = phase9_auth_user_id
    office = await office_factory()
    await _create_membership(
        session,
        office_id=office.id,
        user_id=user_id,
        posx=1,
        posy=2,
    )
    await session.commit()

    from app.models.instance import Instance

    employee = await employee_factory()
    instance = Instance(
        employee_id=employee.id,
        office_id=office.id,
        proxy_token="unused",
    )
    session.add(instance)
    await session.flush()
    membership = await _create_membership(
        session,
        office_id=office.id,
        instance_id=instance.id,
        posx=3,
        posy=4,
    )
    await session.commit()

    response = client.get(
        f"/api/v1/offices/{office.id}/live-status",
        headers=_auth(phase9_auth_token),
    )

    assert response.status_code == 200
    instance_item = next(item for item in response.json() if item["membership_id"] == membership.id)
    assert instance_item["glow"] == {"color": "#94a3b8", "intensity": "static"}
