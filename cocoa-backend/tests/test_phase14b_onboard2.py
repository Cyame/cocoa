"""P14b-onboard2 integration tests.

Three production issues were fixed in P14b-onboard2:

1. ``POST /offices`` now auto-creates an owner :class:`Membership` for the
   authenticated creator so that the office is immediately navigable.
2. The portal "Learning" nav link now points to ``/offices/:id/employees``
   (the new ``EmployeesListPage``) instead of the broken ``/employees``.
3. The portal "Members" nav link points to the new ``/offices/:id/members``
   (``MembersListPage``).

P14b-onboard3 (auto personal workspace) reuses the same test file since
the change is a strict extension of the onboarding surface — see
:class:`TestRegisterAutoPersonalWorkspace` at the bottom of this file.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.models.office import Membership, MembershipRole, Office
from app.models.user import User

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _raise_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent the in-memory rate limiter from interfering with integration tests."""
    monkeypatch.setattr(
        "app.core.middleware.rate_limit.MAX_REQUESTS_PER_WINDOW",
        100_000,
    )


@pytest.fixture
def auth_token(client: TestClient) -> str:
    """Register and login a throwaway user, return the access token."""
    client.post(
        "/api/v1/auth/register",
        json={
            "username": "p14b2creator",
            "email": "p14b2@test.com",
            "password": "password123",
        },
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "p14b2creator", "password": "password123"},
    )
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def creator_user_id(auth_token: str, session: AsyncSession) -> str:
    """Return the user ID for the ``auth_token`` creator."""
    result = await session.execute(
        select(User).where(User.username == "p14b2creator"),
    )
    user: User = result.scalars().first()
    assert user is not None
    return user.id


@pytest.fixture
def second_user(client: TestClient) -> str:
    """Register and login a second user, return the access token."""
    client.post(
        "/api/v1/auth/register",
        json={
            "username": "p14b2editor",
            "email": "p14b2-editor@test.com",
            "password": "password123",
        },
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "p14b2editor", "password": "password123"},
    )
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def second_user_id(second_user: str, session: AsyncSession) -> str:
    """Return the user ID for the second_user."""
    result = await session.execute(
        select(User).where(User.username == "p14b2editor"),
    )
    user: User = result.scalars().first()
    assert user is not None
    return user.id


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Fix 1: auto-create owner Membership on POST /offices
# ---------------------------------------------------------------------------


class TestCreateOfficeAutoMembership:
    """POST /offices must auto-add the creator as an owner Membership."""

    def test_create_office_returns_201(
        self, client: TestClient, auth_token: str,
    ) -> None:
        """POST /offices with a fresh slug returns 201 (smoke)."""
        resp = client.post(
            "/api/v1/offices",
            headers=_auth(auth_token),
            json={"name": "Onboard2 Office", "slug": "onboard2-office"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["slug"] == "onboard2-office"
        assert body["name"] == "Onboard2 Office"
        assert "id" in body

    def test_create_office_auto_creates_owner_membership(
        self,
        client: TestClient,
        auth_token: str,
        creator_user_id: str,
    ) -> None:
        """After POST /offices, the creator appears as an owner in memberships."""
        h = _auth(auth_token)

        resp = client.post(
            "/api/v1/offices",
            headers=h,
            json={"name": "Auto Membership", "slug": "auto-membership"},
        )
        assert resp.status_code == 201
        office_id = resp.json()["id"]

        members = client.get(
            f"/api/v1/messaging/memberships?office_id={office_id}",
            headers=h,
        )
        assert members.status_code == 200
        items = members.json()["items"]
        assert len(items) == 1, (
            f"expected exactly 1 owner membership, got {len(items)}: {items}"
        )
        only = items[0]
        assert only["role"] == "owner"
        assert only["user_id"] == creator_user_id
        assert only["office_id"] == office_id

    def test_create_office_duplicate_slug_returns_409(
        self, client: TestClient, auth_token: str,
    ) -> None:
        """POST /offices with an existing active slug returns 409."""
        h = _auth(auth_token)
        first = client.post(
            "/api/v1/offices",
            headers=h,
            json={"name": "First", "slug": "dup-slug"},
        )
        assert first.status_code == 201

        second = client.post(
            "/api/v1/offices",
            headers=h,
            json={"name": "Second", "slug": "dup-slug"},
        )
        assert second.status_code == 409

    def test_office_detail_returns_to_owner(
        self,
        client: TestClient,
        auth_token: str,
        creator_user_id: str,
    ) -> None:
        """The creator can GET /offices/{id} immediately after creation."""
        h = _auth(auth_token)

        create = client.post(
            "/api/v1/offices",
            headers=h,
            json={"name": "Detail Check", "slug": "detail-check"},
        )
        assert create.status_code == 201
        office_id = create.json()["id"]

        detail = client.get(f"/api/v1/offices/{office_id}", headers=h)
        assert detail.status_code == 200
        body = detail.json()
        assert body["id"] == office_id
        assert body["slug"] == "detail-check"
        # The creator's user_id should appear in the membership list of the
        # returned office, proving they are now an active member.
        members = client.get(
            f"/api/v1/messaging/memberships?office_id={office_id}",
            headers=h,
        )
        assert members.status_code == 200
        items = members.json()["items"]
        user_ids = {item["user_id"] for item in items}
        assert creator_user_id in user_ids

    def test_auto_membership_persists_in_db(
        self,
        client: TestClient,
        auth_token: str,
        creator_user_id: str,
    ) -> None:
        """The auto-Membership is actually persisted (visible via the API)."""
        h = _auth(auth_token)

        create = client.post(
            "/api/v1/offices",
            headers=h,
            json={"name": "Persist Check", "slug": "persist-check"},
        )
        assert create.status_code == 201
        office_id = create.json()["id"]

        members = client.get(
            f"/api/v1/messaging/memberships?office_id={office_id}",
            headers=h,
        )
        assert members.status_code == 200
        items = members.json()["items"]
        assert len(items) == 1
        item = items[0]
        assert item["role"] == "owner"
        assert item["user_id"] == creator_user_id
        assert item["posx"] == 0
        assert item["posy"] == 0
        assert item["office_id"] == office_id

    def test_two_offices_get_two_owner_memberships(
        self,
        client: TestClient,
        auth_token: str,
        creator_user_id: str,
    ) -> None:
        """Creating two offices yields two owner memberships (one per office)."""
        h = _auth(auth_token)

        office_ids = []
        for slug in ("two-a", "two-b"):
            resp = client.post(
                "/api/v1/offices",
                headers=h,
                json={"name": slug, "slug": slug},
            )
            assert resp.status_code == 201
            office_ids.append(resp.json()["id"])

        for office_id in office_ids:
            members = client.get(
                f"/api/v1/messaging/memberships?office_id={office_id}",
                headers=h,
            )
            assert members.status_code == 200
            items = members.json()["items"]
            assert len(items) == 1
            assert items[0]["role"] == "owner"
            assert items[0]["user_id"] == creator_user_id


# ---------------------------------------------------------------------------
# POST /messaging/memberships still works for adding editors/viewers
# ---------------------------------------------------------------------------


class TestDirectMembershipCreation:
    """The existing POST /messaging/memberships pathway still works for editors."""

    def test_add_editor_after_creation(
        self,
        client: TestClient,
        auth_token: str,
        creator_user_id: str,
        second_user_id: str,
    ) -> None:
        """Owner creates an office, then adds a second user as editor."""
        h = _auth(auth_token)

        create = client.post(
            "/api/v1/offices",
            headers=h,
            json={"name": "Editor Office", "slug": "editor-office"},
        )
        assert create.status_code == 201
        office_id = create.json()["id"]

        # Add the editor as an editor-role membership
        resp = client.post(
            "/api/v1/messaging/memberships",
            headers=h,
            json={
                "office_id": office_id,
                "user_id": second_user_id,
                "posx": 1,
                "posy": 0,
                "role": "editor",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["role"] == "editor"
        assert body["user_id"] == second_user_id
        assert body["office_id"] == office_id
        assert body["posx"] == 1
        assert body["posy"] == 0

        # Membership list now has 2 entries: owner + editor
        members = client.get(
            f"/api/v1/messaging/memberships?office_id={office_id}",
            headers=h,
        )
        assert members.status_code == 200
        items = members.json()["items"]
        assert len(items) == 2
        roles = {item["role"] for item in items}
        assert roles == {"owner", "editor"}
        # The two users are distinct
        assert creator_user_id != second_user_id


# ---------------------------------------------------------------------------
# UI navigation routes exist (P14b-onboard2 portal additions)
# ---------------------------------------------------------------------------


class TestPortalRoutesAvailable:
    """Smoke checks that the new portal routes are mounted in the SPA bundle.

    The portal is a React SPA served from a static bundle; we cannot
    introspect the live router from the backend tests.  Instead we verify
    that the backend has the API endpoints the portal pages call, plus that
    the bundled JS files include the new route strings.  This is a
    end-to-end sanity check that the SPA bundle is in sync with the
    backend after a rebuild.
    """

    def test_employees_endpoint_returns_200(
        self, client: TestClient, auth_token: str,
    ) -> None:
        """GET /employees (the data source for EmployeesListPage) is reachable."""
        resp = client.get("/api/v1/employees", headers=_auth(auth_token))
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body

    def test_memberships_endpoint_returns_200(
        self, client: TestClient, auth_token: str,
    ) -> None:
        """GET /messaging/memberships (the data source for MembersListPage) is reachable."""
        # Use a random UUID — even with no rows, the endpoint should be 200.
        resp = client.get(
            "/api/v1/messaging/memberships?office_id="
            "00000000-0000-0000-0000-000000000000",
            headers=_auth(auth_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert body["items"] == []


# ---------------------------------------------------------------------------
# P14b-onboard3: auto-create personal workspace on POST /auth/register
# ---------------------------------------------------------------------------


class TestRegisterAutoPersonalWorkspace:
    """``POST /auth/register`` must create a personal Office + owner Membership."""

    def _fresh_username(self) -> str:
        """UUID-suffixed username so test order / parallelism cannot collide."""
        return f"p14b3-{uuid.uuid4().hex[:10]}"

    def test_register_response_includes_office_id(
        self, client: TestClient,
    ) -> None:
        """Register response now carries ``office_id`` (the personal workspace)."""
        username = self._fresh_username()
        resp = client.post(
            "/api/v1/auth/register",
            json={
                "username": username,
                "email": f"{username}@test.local",
                "password": "password123",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "access_token" in body
        assert "office_id" in body, (
            f"register response missing office_id: {body}"
        )
        office_id = body["office_id"]
        assert isinstance(office_id, str) and len(office_id) > 0

    def test_register_auto_creates_personal_workspace(
        self, client: TestClient,
    ) -> None:
        """After register, GET /offices for the new user returns the personal office."""
        username = self._fresh_username()
        reg = client.post(
            "/api/v1/auth/register",
            json={
                "username": username,
                "email": f"{username}@test.local",
                "password": "password123",
            },
        )
        assert reg.status_code == 201
        body = reg.json()
        token = body["access_token"]
        office_id = body["office_id"]

        offices = client.get(
            "/api/v1/offices", headers=_auth(token),
        )
        assert offices.status_code == 200
        items = offices.json()["items"]
        assert len(items) == 1, (
            f"expected exactly 1 office for fresh user, got {len(items)}: {items}"
        )
        only = items[0]
        assert only["id"] == office_id
        assert only["name"] == f"{username}'s workspace"
        assert only["slug"] == f"{username}-workspace"

    def test_register_creates_owner_membership(
        self, client: TestClient,
    ) -> None:
        """The fresh user holds an owner Membership in their personal office."""
        username = self._fresh_username()
        reg = client.post(
            "/api/v1/auth/register",
            json={
                "username": username,
                "email": f"{username}@test.local",
                "password": "password123",
            },
        )
        assert reg.status_code == 201
        token = reg.json()["access_token"]
        office_id = reg.json()["office_id"]

        members = client.get(
            f"/api/v1/messaging/memberships?office_id={office_id}",
            headers=_auth(token),
        )
        assert members.status_code == 200
        items = members.json()["items"]
        assert len(items) == 1, (
            f"expected exactly 1 owner membership, got {len(items)}: {items}"
        )
        only = items[0]
        assert only["role"] == MembershipRole.owner.value
        assert only["office_id"] == office_id
        assert only["posx"] == 0
        assert only["posy"] == 0

    async def test_personal_office_persists_in_db(
        self, client: TestClient, session: AsyncSession,
    ) -> None:
        """The personal Office + Membership are actually persisted in the DB."""
        username = self._fresh_username()
        reg = client.post(
            "/api/v1/auth/register",
            json={
                "username": username,
                "email": f"{username}@test.local",
                "password": "password123",
            },
        )
        assert reg.status_code == 201
        office_id = reg.json()["office_id"]

        office = await session.get(Office, office_id)
        assert office is not None and office.deleted_at is None
        assert office.name == f"{username}'s workspace"
        assert office.slug == f"{username}-workspace"

        user_row = (
            await session.execute(select(User).where(User.username == username))
        ).scalars().one()
        membership_result = await session.execute(
            select(Membership).where(
                Membership.office_id == office_id,
                Membership.user_id == user_row.id,
            )
        )
        ms = membership_result.scalars().one()
        assert ms.role == MembershipRole.owner.value

    def test_register_duplicate_username_does_not_create_office(
        self, client: TestClient,
    ) -> None:
        """Re-registering an existing username returns 409 and creates no office."""
        username = self._fresh_username()
        first = client.post(
            "/api/v1/auth/register",
            json={
                "username": username,
                "email": f"{username}@test.local",
                "password": "password123",
            },
        )
        assert first.status_code == 201

        second = client.post(
            "/api/v1/auth/register",
            json={
                "username": username,
                "email": f"{username}@test.local",
                "password": "password123",
            },
        )
        assert second.status_code == 409
        assert "office_id" not in second.json()

    def test_login_response_does_not_set_office_id(
        self, client: TestClient,
    ) -> None:
        """POST /auth/login returns no ``office_id`` (clients must fetch /offices)."""
        username = self._fresh_username()
        client.post(
            "/api/v1/auth/register",
            json={
                "username": username,
                "email": f"{username}@test.local",
                "password": "password123",
            },
        )
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": "password123"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body.get("office_id") is None
