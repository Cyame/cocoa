"""Integration tests for P5 messaging endpoints — memberships, corridors,
messages, and scaffold endpoints.

All HTTP tests use the ``client`` fixture (from conftest.py). The
``auth_token`` fixture registers + logs in a throwaway user per test. Each
test runs against its own cloned database.
"""

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.models.user import User
from app.schemas.membership import MembershipCreate

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _raise_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent in-memory rate limiter from interfering with integration tests."""
    monkeypatch.setattr(
        "app.core.middleware.rate_limit.MAX_REQUESTS_PER_WINDOW",
        100_000,
    )


@pytest.fixture
def auth_token(client: TestClient) -> str:
    """Register and login a throwaway user, return access token."""
    client.post("/api/v1/auth/register", json={
        "username": "crudtest",
        "email": "crudtest@test.com",
        "password": "password123",
    })
    resp = client.post("/api/v1/auth/login", json={
        "username": "crudtest",
        "password": "password123",
    })
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def auth_user_id(auth_token: str, session: AsyncSession) -> str:
    """Return the user ID for the ``auth_token`` user."""
    result = await session.execute(
        select(User).where(User.username == "crudtest"),
    )
    user: User = result.scalars().first()
    return user.id


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# =========================================================================
# Group A: Membership CRUD
# =========================================================================


class TestMembershipCrud:
    """CRUD for /api/v1/messaging/memberships."""

    def test_join_office(
        self, client: TestClient, auth_token: str, auth_user_id: str,
    ) -> None:
        """POST /offices auto-creates the creator's owner membership (P14b-onboard2)."""
        h = _auth(auth_token)

        resp = client.post(
            "/api/v1/offices",
            headers=h,
            json={"name": "Membership Office", "slug": "mem-office"},
        )
        assert resp.status_code == 201
        office_id = resp.json()["id"]

        # Auto-membership: creator is added as owner without an explicit join.
        list_resp = client.get(
            f"/api/v1/messaging/memberships?office_id={office_id}",
            headers=h,
        )
        assert list_resp.status_code == 200
        items = list_resp.json()["items"]
        assert len(items) == 1, f"expected 1 owner membership, got {len(items)}"
        body = items[0]
        assert body["office_id"] == office_id
        assert body["user_id"] == auth_user_id
        assert body["role"] == "owner"
        assert "id" in body

    def test_join_office_duplicate(
        self, client: TestClient, auth_token: str, auth_user_id: str,
    ) -> None:
        """Joining the same office twice returns 409."""
        h = _auth(auth_token)

        resp = client.post(
            "/api/v1/offices",
            headers=h,
            json={"name": "Dup Office", "slug": "dup-office"},
        )
        assert resp.status_code == 201
        office_id = resp.json()["id"]

        # P14b-onboard2: creator is auto-added as owner, so re-issuing the
        # owner join now returns 409.
        payload = {
            "office_id": office_id,
            "user_id": auth_user_id,
            "role": "owner",
        }

        resp_duplicate = client.post(
            "/api/v1/messaging/memberships",
            headers=h,
            json=payload,
        )
        assert resp_duplicate.status_code == 409
        assert resp_duplicate.json()["error_code"] == "membership.duplicate"

    def test_change_role(
        self, client: TestClient, auth_token: str, auth_user_id: str,
    ) -> None:
        """PATCH membership role returns 200 with updated role."""
        h = _auth(auth_token)

        resp = client.post(
            "/api/v1/offices",
            headers=h,
            json={"name": "Role Office", "slug": "role-office"},
        )
        assert resp.status_code == 201
        office_id = resp.json()["id"]

        # The creator is auto-added as owner.  Verify role change on that row.
        list_resp = client.get(
            f"/api/v1/messaging/memberships?office_id={office_id}",
            headers=h,
        )
        items = list_resp.json()["items"]
        assert len(items) == 1
        membership_id = items[0]["id"]
        assert items[0]["role"] == "owner"

        resp = client.patch(
            f"/api/v1/messaging/memberships/{membership_id}",
            headers=h,
            json={"role": "editor"},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "editor"

    def test_delete_last_owner_refused(
        self, client: TestClient, auth_token: str, auth_user_id: str,
    ) -> None:
        """Deleting the only owner returns 409."""
        h = _auth(auth_token)

        resp = client.post(
            "/api/v1/offices",
            headers=h,
            json={"name": "Owner Office", "slug": "owner-office"},
        )
        assert resp.status_code == 201
        office_id = resp.json()["id"]

        # The creator is auto-added as the sole owner (P14b-onboard2).
        list_resp = client.get(
            f"/api/v1/messaging/memberships?office_id={office_id}",
            headers=h,
        )
        items = list_resp.json()["items"]
        assert len(items) == 1
        membership_id = items[0]["id"]

        resp = client.delete(
            f"/api/v1/messaging/memberships/{membership_id}",
            headers=h,
        )
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "membership.last_owner"


# =========================================================================
# Group B: Corridor CRUD
# =========================================================================


class TestCorridorCrud:
    """CRUD for /api/v1/messaging/corridors."""

    @pytest.mark.asyncio
    async def test_create_corridor(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        """Register 2 users, both join an office, create corridor → 201."""
        h = _auth(auth_token)

        # 1. Create office (P14b-onboard2: user1 auto-joins as owner)
        resp = client.post(
            "/api/v1/offices",
            headers=h,
            json={"name": "Corr Office", "slug": "corr-office"},
        )
        assert resp.status_code == 201
        office_id = resp.json()["id"]

        # 2. Register user2
        client.post("/api/v1/auth/register", json={
            "username": "corridor_u2",
            "email": "corridor_u2@test.com",
            "password": "password123",
        })
        result = await session.execute(
            select(User).where(User.username == "corridor_u2"),
        )
        user2 = result.scalars().first()
        assert user2 is not None

        # 3. Look up user1's auto-created owner membership
        list_resp = client.get(
            f"/api/v1/messaging/memberships?office_id={office_id}",
            headers=h,
        )
        items = list_resp.json()["items"]
        assert len(items) == 1
        m1_id = items[0]["id"]

        # 4. User2 joins (viewer) at distinct coords (P9 partial unique index)
        resp = client.post(
            "/api/v1/messaging/memberships",
            headers=h,
            json={
                "office_id": office_id,
                "user_id": user2.id,
                "role": "viewer",
                "posx": 100,
                "posy": 100,
            },
        )
        assert resp.status_code == 201
        m2_id = resp.json()["id"]


        # 5. Create corridor u1 → u2
        resp = client.post(
            "/api/v1/messaging/corridors",
            headers=h,
            json={
                "office_id": office_id,
                "from_membership_id": m1_id,
                "to_membership_id": m2_id,
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["from_membership_id"] == m1_id
        assert body["to_membership_id"] == m2_id
        assert body["is_active"] is True

    def test_corridor_self_loop_rejected(
        self, client: TestClient, auth_token: str, auth_user_id: str,
    ) -> None:
        """Corridor with from==to returns 409 (would create cycle)."""
        h = _auth(auth_token)

        resp = client.post(
            "/api/v1/offices",
            headers=h,
            json={"name": "Loop Office", "slug": "loop-office"},
        )
        assert resp.status_code == 201
        office_id = resp.json()["id"]

        # Look up the auto-created owner membership (P14b-onboard2)
        list_resp = client.get(
            f"/api/v1/messaging/memberships?office_id={office_id}",
            headers=h,
        )
        items = list_resp.json()["items"]
        assert len(items) == 1
        m_id = items[0]["id"]

        resp = client.post(
            "/api/v1/messaging/corridors",
            headers=h,
            json={
                "office_id": office_id,
                "from_membership_id": m_id,
                "to_membership_id": m_id,
            },
        )
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "corridor.would_create_cycle"

    def test_list_corridors(
        self, client: TestClient, auth_token: str, auth_user_id: str,
    ) -> None:
        """GET /corridors?office_id=... returns 200 with paginated result."""
        h = _auth(auth_token)

        resp = client.post(
            "/api/v1/offices",
            headers=h,
            json={"name": "List Office", "slug": "list-office"},
        )
        assert resp.status_code == 201
        office_id = resp.json()["id"]

        # Creator is auto-added as owner (P14b-onboard2); corridor list still works.
        resp = client.get(
            "/api/v1/messaging/corridors",
            headers=h,
            params={"office_id": office_id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body

    @pytest.mark.asyncio
    async def test_delete_corridor(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        """DELETE corridor → 204; subsequent GET → 404."""
        h = _auth(auth_token)

        # 1. Create office (P14b-onboard2: user1 auto-joins as owner)
        resp = client.post(
            "/api/v1/offices",
            headers=h,
            json={"name": "Del Office", "slug": "del-office"},
        )
        assert resp.status_code == 201
        office_id = resp.json()["id"]

        # 2. Register user2 for a valid corridor
        client.post("/api/v1/auth/register", json={
            "username": "del_u2",
            "email": "del_u2@test.com",
            "password": "password123",
        })
        result = await session.execute(
            select(User).where(User.username == "del_u2"),
        )
        user2 = result.scalars().first()
        assert user2 is not None

        # 3. Look up user1's auto-created owner membership
        list_resp = client.get(
            f"/api/v1/messaging/memberships?office_id={office_id}",
            headers=h,
        )
        items = list_resp.json()["items"]
        assert len(items) == 1
        m1_id = items[0]["id"]

        resp = client.post(
            "/api/v1/messaging/memberships",
            headers=h,
            json={
                "office_id": office_id,
                "user_id": user2.id,
                "role": "viewer",
                "posx": 200,
                "posy": 200,
            },
        )
        assert resp.status_code == 201
        m2_id = resp.json()["id"]


        # 4. Create corridor
        resp = client.post(
            "/api/v1/messaging/corridors",
            headers=h,
            json={
                "office_id": office_id,
                "from_membership_id": m1_id,
                "to_membership_id": m2_id,
            },
        )
        assert resp.status_code == 201
        corridor_id = resp.json()["id"]

        # 5. Delete
        resp = client.delete(
            f"/api/v1/messaging/corridors/{corridor_id}",
            headers=h,
        )
        assert resp.status_code == 204

        # 6. GET → 404
        resp = client.get(
            f"/api/v1/messaging/corridors/{corridor_id}",
            headers=h,
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "corridor.not_found"


# =========================================================================
# Group C: Meeting / Scheduled-task scaffolds
# =========================================================================


class TestScaffoldEndpoints:
    """Placeholder endpoints that return 501."""

    def test_meeting_scaffold(
        self, client: TestClient,
    ) -> None:
        """POST /meetings returns 501 (no auth required)."""
        resp = client.post("/api/v1/messaging/meetings")
        assert resp.status_code == 501
        body = resp.json()
        assert body["error_code"] == "not_implemented"

    def test_scheduled_task_scaffold(
        self, client: TestClient,
    ) -> None:
        """POST /scheduled-tasks returns 501 (no auth required)."""
        resp = client.post("/api/v1/messaging/scheduled-tasks")
        assert resp.status_code == 501
        body = resp.json()
        assert body["error_code"] == "not_implemented"


# =========================================================================
# Group D: Schema + constant validation
# =========================================================================


class TestSchemaValidation:
    """Pydantic schema and constant validity checks."""

    def test_event_types_exist(self) -> None:
        """MESSAGING_* constants are importable."""
        from app.core.event_types import (
            MESSAGING_ACTIVATION_TRIGGERED,
            MESSAGING_DELIVERY_BLOCKED,
            MESSAGING_MESSAGE_SENT,
        )

        assert MESSAGING_MESSAGE_SENT == "messaging.message_sent"
        assert MESSAGING_DELIVERY_BLOCKED == "messaging.delivery_blocked"
        assert MESSAGING_ACTIVATION_TRIGGERED == "messaging.activation_triggered"

    def test_membership_exclusive_fk(self) -> None:
        """MembershipCreate raises ValidationError when both user_id and
        instance_id are None."""
        with pytest.raises(ValidationError) as exc_info:
            MembershipCreate(
                office_id="test-office",
                user_id=None,
                instance_id=None,
                role="viewer",
            )
        errors = exc_info.value.errors()
        assert any(
            "Exactly one of user_id or instance_id must be set" in e["msg"]
            for e in errors
        ), f"Expected exclusive-FK error, got: {errors}"
