"""P11c integration coverage for the K8s deploy and internal-event wiring."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.v1.deploy import router as deploy_router
from app.api.v1.internal import router as internal_router
from app.core.event_types import HARNESS_CONTROL_SENT
from app.core.event_watcher import EventWatcher
from app.core.events import register_handler
from app.models.deploy_record import DeployRecord, DeployStatus
from app.models.event import Event
from app.services import deploy_service
from app.services.deploy_service import deploy_instance, execute_deploy_pipeline, precheck
from app.services.k8s.event_bus import SSEEvent

_TEST_TOKEN = "p11c-integration-token"


@pytest.fixture
def deploy_app(session: AsyncSession) -> FastAPI:
    app = FastAPI()

    async def override_db():
        yield session

    async def override_user():
        return MagicMock()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    app.include_router(deploy_router, prefix="/api/v1")
    app.include_router(internal_router, prefix="/api/v1")
    return app


@pytest.fixture
def deploy_factory(session: AsyncSession, workspace_factory, entity_factory):
    async def create(name: str, **kwargs):
        workspace = await workspace_factory()
        entity = await entity_factory()
        return await deploy_instance(
            name, "v11", workspace_id=workspace.id, entity_id=entity.id, db=session, **kwargs
        )

    return create


def _install_k8s_mocks(
    monkeypatch: pytest.MonkeyPatch, session: AsyncSession
) -> tuple[MagicMock, list[tuple[str, dict]]]:
    client = MagicMock(name="k8s_client")
    client.ensure_namespace = AsyncMock()
    client.create_or_skip = AsyncMock()
    client.apply = AsyncMock()
    client.scale_deployment = AsyncMock()
    client.get_deployment_status = AsyncMock(return_value={"ready_replicas": 1})
    client.core = MagicMock()
    client.core.delete_namespace = AsyncMock()
    client.apps = MagicMock()
    client.networking = MagicMock()
    monkeypatch.setattr(
        deploy_service,
        "k8s_manager",
        MagicMock(get_gateway_client=AsyncMock(return_value=MagicMock())),
    )
    monkeypatch.setattr(deploy_service, "K8sClient", MagicMock(return_value=client))
    published: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        deploy_service,
        "event_bus",
        MagicMock(publish=lambda event_type, data, event_id=None: published.append((event_type, data))),
    )

    @asynccontextmanager
    async def session_context():
        yield session

    monkeypatch.setattr(deploy_service, "get_session_factory", lambda: lambda: session_context())
    return client, published


@pytest.mark.asyncio
async def test_precheck_pass(session: AsyncSession) -> None:
    result = await precheck("fresh-p11c-name", session)
    assert result.ok is True
    assert result.reason is None


@pytest.mark.asyncio
async def test_precheck_fail_duplicate_name(session: AsyncSession, instance_factory) -> None:
    await instance_factory(workspace_path="duplicate-p11c-name")
    result = await precheck("duplicate-p11c-name", session)
    assert result.ok is False
    assert result.reason == "instance name already exists"


@pytest.mark.asyncio
async def test_deploy_instance_creates_record(session: AsyncSession, deploy_factory) -> None:
    record_id, ctx = await deploy_factory("integration-deploy", proxy_token="proxy-123")
    record = await session.get(DeployRecord, record_id)
    assert record is not None
    assert record.status == DeployStatus.running.value
    assert record.instance_id == ctx.instance_id
    assert ctx.namespace == f"cocoa-inst-{ctx.instance_id.replace('-', '').lower()[:20]}"


@pytest.mark.asyncio
async def test_execute_pipeline_runs_9_steps_mocked(
    session: AsyncSession, deploy_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_id, ctx = await deploy_factory("pipeline-integration")
    client, published = _install_k8s_mocks(monkeypatch, session)
    await execute_deploy_pipeline(ctx)
    progress = [data for event_type, data in published if event_type == "deploy_progress"]
    assert len(progress) == 18
    assert {data["step"] for data in progress} == set(range(1, 10))
    assert client.ensure_namespace.await_count == 1
    assert client.create_or_skip.await_count == 3  # pvc + svc + np
    assert client.apply.await_count == 3  # cm + secret + deployment
    assert client.scale_deployment.await_count == 1
    assert client.get_deployment_status.await_count == 1
    record = await session.get(DeployRecord, record_id)
    assert record is not None
    assert record.status == DeployStatus.success.value


@pytest.mark.asyncio
async def test_cancel_deploy_cleans_namespace(
    session: AsyncSession, deploy_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_id, ctx = await deploy_factory("cancel-integration")
    client, _ = _install_k8s_mocks(monkeypatch, session)
    namespace = await deploy_service.cancel_deploy(record_id)
    assert namespace == f"cocoa-inst-{ctx.instance_id.replace('-', '').lower()[:20]}"
    client.core.delete_namespace.assert_awaited_once_with(namespace)
    record = await session.get(DeployRecord, record_id)
    assert record is not None
    assert record.status == DeployStatus.cancelled.value


@pytest.mark.asyncio
async def test_sse_endpoint_streams_progress(
    deploy_app: FastAPI, deploy_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_id, _ = await deploy_factory("sse-integration")

    async def fake_subscribe(*event_types: str):
        assert event_types == ("deploy_progress",)
        yield SSEEvent("deploy_progress", {"record_id": record_id, "step": 2, "status": "done"})

    monkeypatch.setattr(deploy_service.event_bus, "subscribe", fake_subscribe)
    async with AsyncClient(transport=ASGITransport(app=deploy_app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/deploy/deploy-progress/{record_id}")
    assert response.status_code == 200
    assert "event: deploy_progress" in response.text
    assert '"step": 2' in response.text


@pytest.mark.asyncio
async def test_internal_events_emit_writes_db(
    deploy_app: FastAPI, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COCOA_API_TOKEN", _TEST_TOKEN)
    body = {
        "type": "agent.integration",
        "actor_type": "agent_pod",
        "actor_id": "pod-1",
        "resource_type": "instance",
        "resource_id": "instance-1",
        "payload": {"step": 3},
    }
    async with AsyncClient(transport=ASGITransport(app=deploy_app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/internal/events/emit",
            json=body,
            headers={"Authorization": f"Bearer {_TEST_TOKEN}"},
        )
    assert response.status_code == 201
    event = await session.get(Event, response.json()["event_id"])
    assert event is not None
    assert event.type == body["type"]
    assert event.payload == body["payload"]


@pytest.mark.asyncio
async def test_internal_control_poll_returns_recent(
    deploy_app: FastAPI, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COCOA_API_TOKEN", _TEST_TOKEN)
    event = Event(
        type=HARNESS_CONTROL_SENT,
        actor_type="system",
        resource_type="instance",
        resource_id="poll-instance",
        payload={"action": "kill"},
    )
    session.add(event)
    await session.commit()
    async with AsyncClient(transport=ASGITransport(app=deploy_app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/internal/control/poll?instance_id=poll-instance&last_seen_id=0",
            headers={"Authorization": f"Bearer {_TEST_TOKEN}"},
        )
    assert response.status_code == 200
    assert response.json()["events"][0]["payload"] == {"action": "kill"}
    assert response.json()["last_seen_id"] == event.id


@pytest.mark.asyncio
async def test_proxy_token_env_injection(deploy_factory) -> None:
    _, ctx = await deploy_factory(
        "proxy-integration", proxy_token="secret-proxy", env_vars={"CUSTOM": "value"}
    )
    assert ctx.env_vars["CUSTOM"] == "value"
    assert ctx.env_vars["COCOA_PROXY_TOKEN"] == "secret-proxy"
    assert ctx.env_vars["COCOA_INSTANCE_ID"] == ctx.instance_id
    assert ctx.env_vars["COCOA_POD_MODE"] == "true"
    assert ctx.env_vars["COCOA_API_URL"]
    assert ctx.env_vars["COCOA_WORKSPACE_PATH"] == "/data"


@pytest.mark.asyncio
async def test_event_watcher_dispatches_to_handlers() -> None:
    event = SimpleNamespace(
        id=1,
        type="agent.integration",
        actor_type="agent_pod",
        actor_id="pod-1",
        resource_type="instance",
        resource_id="instance-1",
        payload={"ok": True},
        request_id=None,
        created_at=datetime.now(UTC),
    )
    handler = AsyncMock()
    register_handler("agent.integration", handler)
    result = MagicMock()
    result.scalars.return_value.all.return_value = [event]
    session = AsyncMock()
    session.execute.return_value = result
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=None)
    factory = MagicMock(return_value=context)
    with patch("app.core.event_watcher.get_session_factory", return_value=factory):
        await EventWatcher()._poll_once()
    handler.assert_awaited_once()
    assert handler.await_args.kwargs["payload"] == {"ok": True}
