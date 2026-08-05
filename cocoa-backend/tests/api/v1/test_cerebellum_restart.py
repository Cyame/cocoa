"""v4.9.1 Wave 3: cerebellum restart drives the real instance re-deploy pipeline.

Covers:
- POST /api/v1/central-hubs/{wid}/cerebellum/restart kicks off a real
  deploy (a DeployRecord is created via ``svc_deploy_existing_instance``),
  syncs ``active_hash`` to ``entity.migration_hash``, and emits the
  ``instance.restarted`` audit event.
- The endpoint keeps ``can_operate_workspace`` gating (403 for outsiders).
- A deploy kick-off failure marks the instance ``failed``.

Every DB-touching test uses the conftest per-test cloned database.
"""

from __future__ import annotations

import uuid
from threading import Event as ThreadEvent

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.models.deploy_record import DeployRecord
from app.models.entity import Entity
from app.models.event import Event
from app.models.instance import Instance


@pytest.fixture(autouse=True)
def _raise_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.middleware.rate_limit.MAX_REQUESTS_PER_WINDOW",
        100_000,
    )


def _register(client: TestClient, username: str, email: str) -> str:
    resp = client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": email, "password": "password123"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_workspace(client: TestClient, token: str) -> str:
    slug = f"cerebellum-restart-{uuid.uuid4().hex[:8]}"
    resp = client.post(
        "/api/v1/workspaces",
        headers=_h(token),
        json={"slug": slug, "name": "Cerebellum Restart"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _get_cerebellum(client: TestClient, token: str, workspace_id: str) -> dict:
    resp = client.get(
        f"/api/v1/central-hubs/{workspace_id}/cerebellum",
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestCerebellumRestartPipeline:
    @pytest.mark.asyncio
    async def test_restart_kicks_off_real_deploy(
        self,
        client: TestClient,
        session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        token = _register(client, "cb-restart", "cb-restart@test.com")
        workspace_id = _make_workspace(client, token)
        cerebellum = _get_cerebellum(client, token, workspace_id)
        entity_id = cerebellum["entity_id"]
        instance_id = cerebellum["instance_id"]

        entity = await session.get(Entity, entity_id)
        assert entity is not None
        entity.migration_hash = "c" * 64
        await session.commit()

        pipeline_called = ThreadEvent()

        async def fake_execute(ctx) -> None:
            pipeline_called.set()

        monkeypatch.setattr(
            "app.services.instance_restart.svc_execute_deploy_pipeline",
            fake_execute,
        )

        resp = client.post(
            f"/api/v1/central-hubs/{workspace_id}/cerebellum/restart",
            headers=_h(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["entity_id"] == entity_id
        assert body["instance_id"] == instance_id
        assert body["status"] == "deploying"
        assert body["old_hash"] is None
        assert body["new_hash"] == "c" * 64

        # The deploy pipeline was really kicked off: a DeployRecord was
        # created for the cerebellum instance, and the background task ran.
        assert pipeline_called.wait(timeout=10)
        records = (
            await session.execute(
                select(DeployRecord).where(
                    DeployRecord.instance_id == instance_id,
                    DeployRecord.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        assert len(records) == 1

        # active_hash follows entity.migration_hash after a real restart.
        instance = await session.get(Instance, instance_id)
        assert instance is not None
        assert instance.active_hash == "c" * 64

        # instance.restarted audit event emitted (actor = user).
        events = (
            await session.execute(
                select(Event).where(
                    Event.type == "instance.restarted",
                    Event.resource_id == instance_id,
                )
            )
        ).scalars().all()
        assert len(events) == 1
        assert events[0].payload["old_hash"] is None
        assert events[0].payload["new_hash"] == "c" * 64

    @pytest.mark.asyncio
    async def test_restart_requires_operate_permission(
        self, client: TestClient
    ) -> None:
        owner_token = _register(client, "cb-owner", "cb-owner@test.com")
        workspace_id = _make_workspace(client, owner_token)
        outsider_token = _register(client, "cb-outsider", "cb-outsider@test.com")

        resp = client.post(
            f"/api/v1/central-hubs/{workspace_id}/cerebellum/restart",
            headers=_h(outsider_token),
        )
        assert resp.status_code == 403, resp.text

    @pytest.mark.asyncio
    async def test_restart_marks_failed_when_deploy_kickoff_raises(
        self,
        client: TestClient,
        session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        token = _register(client, "cb-fail", "cb-fail@test.com")
        workspace_id = _make_workspace(client, token)
        cerebellum = _get_cerebellum(client, token, workspace_id)
        instance_id = cerebellum["instance_id"]

        async def fake_deploy(*args, **kwargs):
            raise RuntimeError("deploy kick-off failed")

        monkeypatch.setattr(
            "app.services.instance_restart.svc_deploy_existing_instance",
            fake_deploy,
        )

        resp = client.post(
            f"/api/v1/central-hubs/{workspace_id}/cerebellum/restart",
            headers=_h(token),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "failed"

        instance = await session.get(Instance, instance_id)
        assert instance is not None
        assert instance.status == "failed"

        records = (
            await session.execute(
                select(DeployRecord).where(
                    DeployRecord.instance_id == instance_id,
                    DeployRecord.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        assert records == []
