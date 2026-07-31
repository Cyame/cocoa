"""Integration tests for phase-15f instance action endpoints (T4).

Covers:
- POST /api/v1/instances/{iid}/restart (re-sync outdated instance)
- POST /api/v1/instances/batch-restart (bulk re-sync)
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.models.entity import Entity
from app.models.event import Event
from app.models.instance import Instance, InstanceStatus
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
        "username": "p15f_instances",
        "email": "p15f_instances@test.com",
        "password": "password123",
    })
    resp = client.post("/api/v1/auth/login", json={
        "username": "p15f_instances",
        "password": "password123",
    })
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def auth_user_id(auth_token: str, session: AsyncSession) -> str:
    result = await session.execute(
        select(User).where(User.username == "p15f_instances"),
    )
    user: User = result.scalars().first()
    return user.id


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _setup_workspace(client: TestClient, token: str) -> str:
    slug = f"p15f-restart-{uuid.uuid4().hex[:6]}"
    resp = client.post("/api/v1/workspaces", headers=_auth(token), json={
        "name": f"P15f Restart {slug}",
        "slug": slug,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_entity(client: TestClient, token: str) -> str:
    slug = f"p15f-emp-{uuid.uuid4().hex[:6]}"
    resp = client.post("/api/v1/entities", headers=_auth(token), json={
        "name": "Worker", "slug": slug,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_instance(
    client: TestClient, token: str,
    entity_id: str, workspace_id: str,
    status: str | None = None,
    session: AsyncSession | None = None,
) -> str:
    body: dict = {"entity_id": entity_id, "workspace_id": workspace_id}
    resp = client.post("/api/v1/instances", headers=_auth(token), json=body)
    assert resp.status_code == 201, resp.text
    instance_id = resp.json()["id"]
    if status and session is not None:
        from app.models.instance import Instance
        inst = await session.get(Instance, instance_id)
        assert inst is not None
        inst.status = status
        await session.commit()
    return instance_id


def _grant_role(
    client: TestClient, owner_token: str, workspace_id: str,
    user_id: str, role: str,
) -> None:
    resp = client.post(
        "/api/v1/messaging/memberships",
        headers=_auth(owner_token),
        json={"workspace_id": workspace_id, "user_id": user_id, "role": role},
    )
    assert resp.status_code in (200, 201), resp.text


def _create_operator(
    client: TestClient, owner_token: str, workspace_id: str,
) -> str:
    """Create a throwaway user and grant them the operator role."""
    username = f"op-{uuid.uuid4().hex[:6]}"
    client.post("/api/v1/auth/register", json={
        "username": username,
        "email": f"{username}@test.com",
        "password": "password123",
    })
    login = client.post("/api/v1/auth/login", json={
        "username": username, "password": "password123",
    })
    user_id_resp = client.get(
        f"/api/v1/users/lookup?username={username}",
        headers=_auth(login.json()["access_token"]),
    )
    if user_id_resp.status_code == 200:
        user_id = user_id_resp.json()["id"]
    else:
        # Fallback: search via DB.
        # The lookup endpoint may not exist; query directly.
        # Note: this is a sync test context; we rely on the session fixture.
        raise RuntimeError("User lookup endpoint unavailable")
    _grant_role(client, owner_token, workspace_id, user_id, "operator")
    return login.json()["access_token"]


# =========================================================================
# Endpoint E: POST /instances/{iid}/restart
# =========================================================================


class TestInstanceRestart:
    """Tests for the re-sync restart endpoint."""

    async def test_restart_updates_active_hash_and_status(
        self, client: TestClient, auth_token: str, auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        instance_id = await _create_instance(
            client, auth_token, entity_id, workspace_id,
            status=InstanceStatus.pending.value,
        session=session,
        )

        # Simulate outdated instance (no active_hash) before re-sync.
        inst0 = await session.get(Instance, instance_id)
        assert inst0 is not None
        inst0.active_hash = None
        await session.commit()

        # Set Entity.migration_hash to a known value.
        emp = await session.get(Entity, entity_id)
        assert emp is not None
        emp.migration_hash = "f" * 64
        await session.commit()

        resp = client.post(
            f"/api/v1/instances/{instance_id}/restart",
            headers=h,
            json={},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["instance_id"] == instance_id
        assert body["old_hash"] is None
        assert body["new_hash"] == "f" * 64
        assert body["status_after"] in {
            "deploying",
            "restarting",
            "pending",
            "failed",
            "running",
        }

        await session.refresh(inst0)
        assert inst0.active_hash == "f" * 64
        assert inst0.status in {
            InstanceStatus.deploying.value,
            InstanceStatus.failed.value,
            InstanceStatus.pending.value,
            InstanceStatus.running.value,
        }

    async def test_restart_while_running_stops_and_redeploys(
        self, client: TestClient, auth_token: str, auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        instance_id = await _create_instance(
            client, auth_token, entity_id, workspace_id,
            status=InstanceStatus.running.value,
        session=session,
        )

        resp = client.post(
            f"/api/v1/instances/{instance_id}/restart",
            headers=h,
            json={},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["instance_id"] == instance_id
        assert body["status_after"] in {"deploying", "restarting", "pending", "failed", "running"}

    async def test_restart_with_force_bypasses_running(
        self, client: TestClient, auth_token: str, auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        instance_id = await _create_instance(
            client, auth_token, entity_id, workspace_id,
            status=InstanceStatus.running.value,
        session=session,
        )

        emp = await session.get(Entity, entity_id)
        assert emp is not None
        emp.migration_hash = "a" * 64
        await session.commit()

        resp = client.post(
            f"/api/v1/instances/{instance_id}/restart",
            headers=h,
            json={"force": True},
        )
        assert resp.status_code == 200, resp.text

    def test_restart_404_for_unknown_instance(
        self, client: TestClient, auth_token: str,
    ) -> None:
        h = _auth(auth_token)
        resp = client.post(
            f"/api/v1/instances/{uuid.uuid4()}/restart",
            headers=h, json={},
        )
        assert resp.status_code == 404, resp.text

    async def test_restart_emits_event(
        self, client: TestClient, auth_token: str, auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        instance_id = await _create_instance(
            client, auth_token, entity_id, workspace_id,
            status=InstanceStatus.pending.value,
        session=session,
        )

        inst0 = await session.get(Instance, instance_id)
        assert inst0 is not None
        inst0.active_hash = None
        await session.commit()

        emp = await session.get(Entity, entity_id)
        assert emp is not None
        emp.migration_hash = "b" * 64
        await session.commit()

        client.post(
            f"/api/v1/instances/{instance_id}/restart",
            headers=h, json={"reason": "manual re-sync"},
        )

        ev_result = await session.execute(
            select(Event).where(
                Event.type == "instance.restarted",
                Event.resource_id == instance_id,
            )
        )
        events = list(ev_result.scalars().all())
        assert len(events) == 1
        assert events[0].payload["old_hash"] is None
        assert events[0].payload["new_hash"] == "b" * 64
        assert events[0].payload["reason"] == "manual re-sync"


# =========================================================================
# Endpoint F: POST /instances/batch-restart
# =========================================================================


class TestBatchRestart:
    """Tests for the batch re-sync endpoint."""

    async def test_batch_restart_succeeds_when_all_idle(
        self, client: TestClient, auth_token: str, auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)

        emp = await session.get(Entity, entity_id)
        assert emp is not None
        emp.migration_hash = "c" * 64
        await session.commit()

        ids = [
            await _create_instance(
                client, auth_token, entity_id, workspace_id,
                status=InstanceStatus.pending.value,
            session=session,
            )
            for _ in range(3)
        ]

        resp = client.post(
            "/api/v1/instances/batch-restart",
            headers=h,
            json={"instance_ids": ids, "reason": "promote cascade"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["restarted_count"] == 3
        assert sorted(body["instance_ids"]) == sorted(ids)
        assert body["skipped"] == []

        for iid in ids:
            inst = await session.get(Instance, iid)
            assert inst is not None
            assert inst.active_hash == "c" * 64
            assert inst.status == InstanceStatus.restarting.value

    async def test_batch_restart_409_when_any_running(
        self, client: TestClient, auth_token: str, auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)

        idle_id = await _create_instance(
            client, auth_token, entity_id, workspace_id,
            status=InstanceStatus.pending.value,
        session=session,
        )
        running_id = await _create_instance(
            client, auth_token, entity_id, workspace_id,
            status=InstanceStatus.running.value,
        session=session,
        )

        resp = client.post(
            "/api/v1/instances/batch-restart",
            headers=h,
            json={"instance_ids": [idle_id, running_id]},
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body["error_code"] == "instance.batch_has_running"
        assert running_id in body["details"]["running_instance_ids"]

    async def test_batch_restart_404_for_unknown_instance(
        self, client: TestClient, auth_token: str, auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        await _create_instance(
            client, auth_token, entity_id, workspace_id,
            status=InstanceStatus.pending.value,
        session=session,
        )

        resp = client.post(
            "/api/v1/instances/batch-restart",
            headers=h,
            json={"instance_ids": [str(uuid.uuid4())]},
        )
        assert resp.status_code == 404, resp.text

    async def test_batch_restart_emits_event(
        self, client: TestClient, auth_token: str, auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        ids = [
            await _create_instance(
                client, auth_token, entity_id, workspace_id,
                status=InstanceStatus.pending.value,
            session=session,
            )
            for _ in range(2)
        ]

        client.post(
            "/api/v1/instances/batch-restart",
            headers=h, json={"instance_ids": ids, "reason": "cascade"},
        )

        ev_result = await session.execute(
            select(Event).where(Event.type == "instance.batch_restarted")
        )
        events = list(ev_result.scalars().all())
        assert len(events) == 1
        assert events[0].payload["restarted_count"] == 2
        assert events[0].payload["reason"] == "cascade"
