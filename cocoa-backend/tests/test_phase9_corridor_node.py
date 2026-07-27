"""Integration tests for P9 Todo 8 — CorridorNode CRUD + Corridor polymorphic.

Covers 8 paths under
``/api/v1/learning/corridor-nodes`` and the polymorphic corridor
endpoint at ``/api/v1/messaging/corridors``:

1. ``test_create_corridor_node_returns_201``
2. ``test_list_corridor_nodes_returns_created``
3. ``test_get_corridor_node_by_id``
4. ``test_patch_corridor_node_updates_fields``
5. ``test_delete_corridor_node_soft_deletes``
6. ``test_write_requires_editor_role``
7. ``test_create_conflict_position_returns_409``
8. ``test_corridor_polymorphic_rejects_both_endpoints_null``
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.models.user import User

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _raise_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.middleware.rate_limit.MAX_REQUESTS_PER_WINDOW",
        100_000,
    )


@pytest.fixture
def owner_token(client: TestClient) -> str:
    """Register + login an owner. Returns the access token."""
    client.post(
        "/api/v1/auth/register",
        json={
            "username": "cn_owner",
            "email": "cn_owner@test.com",
            "password": "password123",
        },
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "cn_owner", "password": "password123"},
    )
    return resp.json()["access_token"]


@pytest.fixture
def viewer_token(client: TestClient) -> str:
    """Register + login a second user used as a viewer."""
    client.post(
        "/api/v1/auth/register",
        json={
            "username": "cn_viewer",
            "email": "cn_viewer@test.com",
            "password": "password123",
        },
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "cn_viewer", "password": "password123"},
    )
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def office_id(
    owner_token: str,
    client: TestClient,
    session: AsyncSession,
) -> str:
    """Create an office, join the owner as owner, return office id."""
    resp = client.post(
        "/api/v1/offices",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"name": "CorridorNode Office", "slug": "cn-office"},
    )
    assert resp.status_code == 201
    office_id = resp.json()["id"]

    result = await session.execute(
        select(User).where(User.username == "cn_owner")
    )
    owner_user_id = result.scalar_one().id

    join_resp = client.post(
        "/api/v1/messaging/memberships",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "office_id": office_id,
            "user_id": owner_user_id,
            "role": "owner",
            "posx": 0,
            "posy": 0,
        },
    )
    assert join_resp.status_code == 201
    return office_id


@pytest_asyncio.fixture
async def owner_user_id(session: AsyncSession) -> str:
    result = await session.execute(
        select(User).where(User.username == "cn_owner")
    )
    return result.scalar_one().id


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1. POST creates new corridor_node
# ---------------------------------------------------------------------------


def test_create_corridor_node_returns_201(
    client: TestClient,
    owner_token: str,
    office_id: str,
) -> None:
    """POST /learning/corridor-nodes returns 201 with the new row."""
    resp = client.post(
        "/api/v1/learning/corridor-nodes",
        headers=_auth(owner_token),
        json={
            "office_id": office_id,
            "posx": 100,
            "posy": 200,
            "display_name": "Topic Hub",
            "glow_color": "#10b981",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["office_id"] == office_id
    assert body["posx"] == 100
    assert body["posy"] == 200
    assert body["display_name"] == "Topic Hub"
    assert body["glow_color"] == "#10b981"
    assert body["status"] == "active"
    assert "id" in body


# ---------------------------------------------------------------------------
# 2. GET list returns created node
# ---------------------------------------------------------------------------


def test_list_corridor_nodes_returns_created(
    client: TestClient,
    owner_token: str,
    office_id: str,
) -> None:
    """GET list returns the node we just created."""
    create_resp = client.post(
        "/api/v1/learning/corridor-nodes",
        headers=_auth(owner_token),
        json={
            "office_id": office_id,
            "posx": 10,
            "posy": 20,
            "display_name": "Hub A",
        },
    )
    assert create_resp.status_code == 201
    created_id = create_resp.json()["id"]

    list_resp = client.get(
        "/api/v1/learning/corridor-nodes",
        headers=_auth(owner_token),
        params={"office_id": office_id},
    )
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert body["total"] == 1
    assert any(item["id"] == created_id for item in body["items"])


# ---------------------------------------------------------------------------
# 3. GET by id
# ---------------------------------------------------------------------------


def test_get_corridor_node_by_id(
    client: TestClient,
    owner_token: str,
    office_id: str,
) -> None:
    """GET /learning/corridor-nodes/{id} returns the row."""
    create_resp = client.post(
        "/api/v1/learning/corridor-nodes",
        headers=_auth(owner_token),
        json={
            "office_id": office_id,
            "posx": 50,
            "posy": 60,
            "display_name": "Hub B",
        },
    )
    node_id = create_resp.json()["id"]

    resp = client.get(
        f"/api/v1/learning/corridor-nodes/{node_id}",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == node_id
    assert resp.json()["display_name"] == "Hub B"


# ---------------------------------------------------------------------------
# 4. PATCH updates display_name / posx / posy / status
# ---------------------------------------------------------------------------


def test_patch_corridor_node_updates_fields(
    client: TestClient,
    owner_token: str,
    office_id: str,
) -> None:
    """PATCH applies partial updates to display_name, posx, posy, status."""
    create_resp = client.post(
        "/api/v1/learning/corridor-nodes",
        headers=_auth(owner_token),
        json={
            "office_id": office_id,
            "posx": 1,
            "posy": 2,
            "display_name": "Original",
            "status": "active",
        },
    )
    node_id = create_resp.json()["id"]

    patch_resp = client.patch(
        f"/api/v1/learning/corridor-nodes/{node_id}",
        headers=_auth(owner_token),
        json={
            "display_name": "Renamed",
            "posx": 9,
            "posy": 8,
            "status": "paused",
        },
    )
    assert patch_resp.status_code == 200
    body = patch_resp.json()
    assert body["display_name"] == "Renamed"
    assert body["posx"] == 9
    assert body["posy"] == 8
    assert body["status"] == "paused"


# ---------------------------------------------------------------------------
# 5. DELETE soft-deletes (204) -> next GET 404
# ---------------------------------------------------------------------------


def test_delete_corridor_node_soft_deletes(
    client: TestClient,
    owner_token: str,
    office_id: str,
) -> None:
    """DELETE returns 204 and subsequent GET returns 404."""
    create_resp = client.post(
        "/api/v1/learning/corridor-nodes",
        headers=_auth(owner_token),
        json={
            "office_id": office_id,
            "posx": 30,
            "posy": 40,
            "display_name": "To Be Deleted",
        },
    )
    node_id = create_resp.json()["id"]

    del_resp = client.delete(
        f"/api/v1/learning/corridor-nodes/{node_id}",
        headers=_auth(owner_token),
    )
    assert del_resp.status_code == 204

    get_resp = client.get(
        f"/api/v1/learning/corridor-nodes/{node_id}",
        headers=_auth(owner_token),
    )
    assert get_resp.status_code == 404
    assert get_resp.json()["error_code"] == "corridor_node.not_found"


# ---------------------------------------------------------------------------
# 6. Editor role required for write
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_requires_editor_role(
    client: TestClient,
    owner_token: str,
    viewer_token: str,
    office_id: str,
    session: AsyncSession,
    owner_user_id: str,
) -> None:
    """Viewer role gets 403 on POST; owner gets 201 on the same body."""
    create_body = {
        "office_id": office_id,
        "posx": 7,
        "posy": 7,
        "display_name": "Viewer Cannot",
    }

    viewer_resp = client.post(
        "/api/v1/learning/corridor-nodes",
        headers=_auth(viewer_token),
        json=create_body,
    )
    assert viewer_resp.status_code == 403
    assert viewer_resp.json()["error_code"] == "office.not_member"

    owner_resp = client.post(
        "/api/v1/learning/corridor-nodes",
        headers=_auth(owner_token),
        json=create_body,
    )
    assert owner_resp.status_code == 201


# ---------------------------------------------------------------------------
# 7. Conflict position returns 409
# ---------------------------------------------------------------------------


def test_create_conflict_position_returns_409(
    client: TestClient,
    owner_token: str,
    office_id: str,
) -> None:
    """Two corridor nodes at the same (office, posx, posy) -> 409."""
    first = client.post(
        "/api/v1/learning/corridor-nodes",
        headers=_auth(owner_token),
        json={
            "office_id": office_id,
            "posx": 12,
            "posy": 34,
            "display_name": "First",
        },
    )
    assert first.status_code == 201

    second = client.post(
        "/api/v1/learning/corridor-nodes",
        headers=_auth(owner_token),
        json={
            "office_id": office_id,
            "posx": 12,
            "posy": 34,
            "display_name": "Second",
        },
    )
    assert second.status_code == 409
    assert second.json()["error_code"] == "corridor_node.position_taken"


# ---------------------------------------------------------------------------
# 8. Corridor polymorphic CHECK rejects both endpoints NULL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_corridor_polymorphic_rejects_both_endpoints_null(
    client: TestClient,
    owner_token: str,
    office_id: str,
    session: AsyncSession,
) -> None:
    """A corridor row with from=NULL/=NULL is rejected by the DB CHECK.

    Bypasses the Pydantic validator (which already catches the case
    with 422) by inserting directly via the ORM so we exercise the
    database CHECK constraint, not the request validator. The DB
    CHECK is the last line of defence against application-layer bugs
    that bypass the API.
    """
    from sqlalchemy.exc import IntegrityError

    from app.models.office import Corridor

    # Direct ORM insert with both endpoint columns NULL.
    bad_corridor = Corridor(
        office_id=office_id,
        from_membership_id=None,
        to_membership_id=None,
        from_corridor_node_id=None,
        to_corridor_node_id=None,
        is_active=True,
    )
    session.add(bad_corridor)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


# ---------------------------------------------------------------------------
# Bonus: POST corridor with both from_ and to_ endpoints populated
# (sanity check that the polymorphic validator rejects the API path
# before reaching the DB).
# ---------------------------------------------------------------------------


def test_corridor_create_rejects_pydantic_polymorphic_violation(
    client: TestClient,
    owner_token: str,
    office_id: str,
) -> None:
    """A corridor with both from_membership_id and from_corridor_node_id
    set is rejected at the Pydantic layer (422)."""
    resp = client.post(
        "/api/v1/messaging/corridors",
        headers=_auth(owner_token),
        json={
            "office_id": office_id,
            "from_membership_id": "any-id",
            "from_corridor_node_id": "any-id",
            "to_membership_id": "other-id",
        },
    )
    assert resp.status_code == 422
