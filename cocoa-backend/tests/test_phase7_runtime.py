"""Integration tests for P7 Instance Runtime — CRUD, lifecycle state machine,
workspace isolation, and event emission.

All tests use the ``client`` fixture (isolated DB clone + JWT auth).
Each test creates its own office/membership/employee data.
"""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.models.event import Event
from app.models.user import User


@pytest.fixture(autouse=True)
def _raise_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.middleware.rate_limit.MAX_REQUESTS_PER_WINDOW",
        100_000,
    )


@pytest.fixture
def auth_token(client: TestClient) -> str:
    client.post("/api/v1/auth/register", json={
        "username": "runtime_test",
        "email": "runtime_test@test.com",
        "password": "password123",
    })
    resp = client.post("/api/v1/auth/login", json={
        "username": "runtime_test",
        "password": "password123",
    })
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def auth_user_id(auth_token: str, session: AsyncSession) -> str:
    result = await session.execute(
        select(User).where(User.username == "runtime_test"),
    )
    user: User = result.scalars().first()
    return user.id


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _setup_office_and_membership(
    client: TestClient,
    token: str,
    user_id: str,
    office_name: str = "Runtime Office",
    office_slug: str = "runtime-office",
) -> str:
    """Create an office; the creator is auto-added as owner (P14b-onboard2).

    Before P14b-onboard2 the helper also called
    ``POST /api/v1/messaging/memberships`` to attach the creator as an owner.
    That step now returns 409 Conflict because office creation already adds the
    owner, so the manual call has been removed.  ``user_id`` is kept in the
    signature for backward compatibility with existing call sites.
    """
    h = _auth(token)
    resp = client.post("/api/v1/offices", headers=h, json={
        "name": office_name,
        "slug": office_slug,
    })
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_employee(client: TestClient, token: str, slug: str, name: str) -> str:
    resp = client.post("/api/v1/employees", headers=_auth(token), json={
        "name": name,
        "slug": slug,
    })
    assert resp.status_code == 201
    return resp.json()["id"]


# =========================================================================
# Instance CRUD
# =========================================================================


class TestInstanceCrud:
    """CRUD for /api/v1/instances."""

    def test_create_instance(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
    ) -> None:
        """POST /api/v1/instances returns 201 with status=creating, proxy_token set,
        workspace_path auto-generated."""
        h = _auth(auth_token)
        office_id = _setup_office_and_membership(
            client, auth_token, auth_user_id,
        )
        employee_id = _create_employee(
            client, auth_token, "creater-emp", "Creator Employee",
        )

        resp = client.post("/api/v1/instances", headers=h, json={
            "employee_id": employee_id,
            "office_id": office_id,
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "creating"
        assert body["proxy_token"] is not None
        assert len(body["proxy_token"]) > 0
        assert body["workspace_path"] is not None
        assert "id" in body

    def test_list_instances(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
    ) -> None:
        """GET /api/v1/instances returns paginated list; ?status= filter works."""
        h = _auth(auth_token)
        office_id = _setup_office_and_membership(
            client, auth_token, auth_user_id,
        )
        employee_id = _create_employee(
            client, auth_token, "lister-emp", "Lister Employee",
        )

        # Create two instances with different statuses
        resp1 = client.post("/api/v1/instances", headers=h, json={
            "employee_id": employee_id,
            "office_id": office_id,
        })
        assert resp1.status_code == 201
        inst1_id = resp1.json()["id"]

        resp2 = client.post("/api/v1/instances", headers=h, json={
            "employee_id": employee_id,
            "office_id": office_id,
        })
        assert resp2.status_code == 201
        inst2_id = resp2.json()["id"]

        # Fail inst2 so it has a different status
        client.post(
            f"/api/v1/instances/{inst2_id}/fail",
            headers=h,
            json={"reason": "test"},
        )

        # List all — should see both
        resp = client.get("/api/v1/instances", headers=h)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 2
        ids = {item["id"] for item in body["items"]}
        assert inst1_id in ids
        assert inst2_id in ids

        # Filter by status=creating — only inst1
        resp = client.get("/api/v1/instances?status=creating", headers=h)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == inst1_id

    def test_delete_instance_when_not_running(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
    ) -> None:
        """Create instance, fail it (not running), then DELETE returns 204;
        subsequent GET returns 404."""
        h = _auth(auth_token)
        office_id = _setup_office_and_membership(
            client, auth_token, auth_user_id,
        )
        employee_id = _create_employee(
            client, auth_token, "deleter-emp", "Deleter Employee",
        )

        resp = client.post("/api/v1/instances", headers=h, json={
            "employee_id": employee_id,
            "office_id": office_id,
        })
        assert resp.status_code == 201
        inst_id = resp.json()["id"]

        # Transition to failed (not running)
        fail_resp = client.post(
            f"/api/v1/instances/{inst_id}/fail",
            headers=h,
            json={"reason": "cleanup"},
        )
        assert fail_resp.status_code == 200
        assert fail_resp.json()["status"] == "failed"

        # Delete
        del_resp = client.delete(f"/api/v1/instances/{inst_id}", headers=h)
        assert del_resp.status_code == 204

        # Get → 404
        get_resp = client.get(f"/api/v1/instances/{inst_id}", headers=h)
        assert get_resp.status_code == 404
        assert get_resp.json()["error_code"] == "instance.not_found"


# =========================================================================
# Instance State Machine
# =========================================================================


class TestInstanceStateMachine:
    """Lifecycle state-machine transitions for action endpoints."""

    @pytest.mark.asyncio
    async def test_deploy_from_creating_succeeds(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        """create → POST deploy → 200 status='deploying'; verify INSTANCE_DEPLOYED event."""
        h = _auth(auth_token)
        office_id = _setup_office_and_membership(
            client, auth_token, auth_user_id,
        )
        employee_id = _create_employee(
            client, auth_token, "deployer-emp", "Deployer Employee",
        )

        resp = client.post("/api/v1/instances", headers=h, json={
            "employee_id": employee_id,
            "office_id": office_id,
        })
        assert resp.status_code == 201
        inst_id = resp.json()["id"]

        deploy_resp = client.post(
            f"/api/v1/instances/{inst_id}/deploy",
            headers=h,
        )
        assert deploy_resp.status_code == 200
        assert deploy_resp.json()["status"] == "deploying"

        # Roll back any pending implicit transaction so the query sees
        # the latest committed state (the session may have autobegun
        # during fixture resolution).
        await session.rollback()

        result = await session.execute(
            select(Event).where(
                Event.resource_type == "instance",
                Event.resource_id == inst_id,
                Event.type == "instance.deployed",
            ),
        )
        events = result.scalars().all()
        assert len(events) == 1

    def test_deploy_from_running_rejected(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
    ) -> None:
        """create → deploy → start (status=running) → POST deploy returns 409."""
        h = _auth(auth_token)
        office_id = _setup_office_and_membership(
            client, auth_token, auth_user_id,
        )
        employee_id = _create_employee(
            client, auth_token, "runner-emp", "Runner Employee",
        )

        resp = client.post("/api/v1/instances", headers=h, json={
            "employee_id": employee_id,
            "office_id": office_id,
        })
        assert resp.status_code == 201
        inst_id = resp.json()["id"]

        client.post(f"/api/v1/instances/{inst_id}/deploy", headers=h)
        start_resp = client.post(
            f"/api/v1/instances/{inst_id}/start",
            headers=h,
        )
        assert start_resp.status_code == 200
        assert start_resp.json()["status"] == "running"

        # Deploy from running must be rejected
        deploy_resp = client.post(
            f"/api/v1/instances/{inst_id}/deploy",
            headers=h,
        )
        assert deploy_resp.status_code == 409
        assert deploy_resp.json()["error_code"] == "instance.invalid_transition"

    def test_full_lifecycle(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
    ) -> None:
        """create → deploy → start → stop → delete; running→delete blocked."""
        h = _auth(auth_token)
        office_id = _setup_office_and_membership(
            client, auth_token, auth_user_id,
        )
        employee_id = _create_employee(
            client, auth_token, "lifecycle-emp", "Lifecycle Employee",
        )

        # create
        resp = client.post("/api/v1/instances", headers=h, json={
            "employee_id": employee_id,
            "office_id": office_id,
        })
        assert resp.status_code == 201
        inst_id = resp.json()["id"]
        assert resp.json()["status"] == "creating"

        # deploy
        resp = client.post(f"/api/v1/instances/{inst_id}/deploy", headers=h)
        assert resp.status_code == 200
        assert resp.json()["status"] == "deploying"

        # start
        resp = client.post(f"/api/v1/instances/{inst_id}/start", headers=h)
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

        # Delete while running must be blocked
        del_resp = client.delete(f"/api/v1/instances/{inst_id}", headers=h)
        assert del_resp.status_code == 409
        assert del_resp.json()["error_code"] == "instance.still_running"

        # stop
        resp = client.post(f"/api/v1/instances/{inst_id}/stop", headers=h)
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

        # delete (now allowed)
        del_resp = client.delete(f"/api/v1/instances/{inst_id}", headers=h)
        assert del_resp.status_code == 204

    @pytest.mark.asyncio
    async def test_fail_transition(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        """create → POST /fail {"reason":"crash"} → 200 status='failed';
        verify INSTANCE_FAILED event with reason in payload."""
        h = _auth(auth_token)
        office_id = _setup_office_and_membership(
            client, auth_token, auth_user_id,
        )
        employee_id = _create_employee(
            client, auth_token, "failer-emp", "Failer Employee",
        )

        resp = client.post("/api/v1/instances", headers=h, json={
            "employee_id": employee_id,
            "office_id": office_id,
        })
        assert resp.status_code == 201
        inst_id = resp.json()["id"]

        fail_resp = client.post(
            f"/api/v1/instances/{inst_id}/fail",
            headers=h,
            json={"reason": "crash"},
        )
        assert fail_resp.status_code == 200
        assert fail_resp.json()["status"] == "failed"

        await session.rollback()

        result = await session.execute(
            select(Event).where(
                Event.resource_type == "instance",
                Event.resource_id == inst_id,
                Event.type == "instance.failed",
            ),
        )
        events = result.scalars().all()
        assert len(events) == 1
        assert events[0].payload.get("reason") == "crash"


# =========================================================================
# Workspace Isolation
# =========================================================================


class TestInstanceIsolation:
    """Multi-instance workspace_path isolation."""

    def test_two_instances_different_workspace_paths(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
    ) -> None:
        """Create 2 instances for same employee — both have different workspace_path."""
        h = _auth(auth_token)
        office_id = _setup_office_and_membership(
            client, auth_token, auth_user_id,
        )
        employee_id = _create_employee(
            client, auth_token, "iso-emp", "Isolation Employee",
        )

        resp1 = client.post("/api/v1/instances", headers=h, json={
            "employee_id": employee_id,
            "office_id": office_id,
        })
        assert resp1.status_code == 201
        ws1 = resp1.json()["workspace_path"]

        resp2 = client.post("/api/v1/instances", headers=h, json={
            "employee_id": employee_id,
            "office_id": office_id,
        })
        assert resp2.status_code == 201
        ws2 = resp2.json()["workspace_path"]

        assert ws1 != ws2
        assert ws1 is not None
        assert ws2 is not None


# =========================================================================
# Instance Lifecycle Events
# =========================================================================


class TestInstanceEvents:
    """Event emission verification via events table."""

    @pytest.mark.asyncio
    async def test_lifecycle_events_create_and_deploy(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        """create → deploy → query events → INSTANCE_CREATED and INSTANCE_DEPLOYED."""
        h = _auth(auth_token)
        office_id = _setup_office_and_membership(
            client, auth_token, auth_user_id,
        )
        employee_id = _create_employee(
            client, auth_token, "event-cd-emp", "Event CD Employee",
        )

        resp = client.post("/api/v1/instances", headers=h, json={
            "employee_id": employee_id,
            "office_id": office_id,
        })
        assert resp.status_code == 201
        inst_id = resp.json()["id"]

        client.post(f"/api/v1/instances/{inst_id}/deploy", headers=h)

        await session.rollback()

        result = await session.execute(
            select(Event)
            .where(Event.resource_type == "instance")
            .order_by(Event.created_at),
        )
        events = result.scalars().all()
        event_types = [e.type for e in events]

        assert "instance.created" in event_types
        assert "instance.deployed" in event_types

        # INSTANCE_DEPLOYED has resource_id set correctly
        deploy_events = [e for e in events if e.type == "instance.deployed"]
        assert len(deploy_events) == 1
        assert deploy_events[0].resource_id == inst_id

    @pytest.mark.asyncio
    async def test_lifecycle_events_full_cycle(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        """create → deploy → start → fail → query events →
        INSTANCE_CREATED, INSTANCE_DEPLOYED, INSTANCE_STARTED, INSTANCE_FAILED."""
        h = _auth(auth_token)
        office_id = _setup_office_and_membership(
            client, auth_token, auth_user_id,
        )
        employee_id = _create_employee(
            client, auth_token, "event-full-emp", "Event Full Employee",
        )

        resp = client.post("/api/v1/instances", headers=h, json={
            "employee_id": employee_id,
            "office_id": office_id,
        })
        assert resp.status_code == 201
        inst_id = resp.json()["id"]

        client.post(f"/api/v1/instances/{inst_id}/deploy", headers=h)
        client.post(f"/api/v1/instances/{inst_id}/start", headers=h)
        client.post(
            f"/api/v1/instances/{inst_id}/fail",
            headers=h,
            json={"reason": "oom"},
        )

        await session.rollback()

        result = await session.execute(
            select(Event)
            .where(Event.resource_type == "instance")
            .order_by(Event.created_at),
        )
        events = result.scalars().all()
        event_types = [e.type for e in events]

        assert "instance.created" in event_types
        assert "instance.deployed" in event_types
        assert "instance.started" in event_types
        assert "instance.failed" in event_types

        # Deploy/running/failed events have resource_id set correctly
        for e in events:
            if e.type != "instance.created":
                assert e.resource_id == inst_id
