"""P11c unit tests for ``app.services.deploy_service``.

The three must-have surfaces (per P11c Todo 1 brief):

1. ``test_precheck_pass`` — a fresh ``name`` returns ``PrecheckResult(ok=True)``.
2. ``test_deploy_instance_creates_record`` — ``deploy_instance`` creates the
   Instance + DeployRecord pair and returns ``(record_id, ctx)``.
3. ``test_execute_pipeline_runs_9_steps_mocked`` — the async pipeline
   publishes 9 SSE steps and transitions the DeployRecord to ``success``.

All K8s API calls in test 3 are mocked; no real cluster is touched.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deploy_record import DeployRecord, DeployStatus
from app.services.deploy_service import (
    PrecheckResult,
    deploy_instance,
    execute_deploy_pipeline,
    precheck,
)

# ── 1. precheck passes for a fresh name ────────────────────────────


@pytest.mark.asyncio
async def test_precheck_pass(session: AsyncSession) -> None:
    """``precheck("fresh-name", db)`` returns ok=True when no Instance exists."""
    result = await precheck("fresh-name", session)
    assert isinstance(result, PrecheckResult)
    assert result.ok is True
    assert result.reason is None


# ── 2. deploy_instance creates Instance + DeployRecord ─────────────


@pytest.mark.asyncio
async def test_deploy_instance_creates_record(
    session: AsyncSession,
    workspace_factory,
    entity_factory,
) -> None:
    """``deploy_instance`` persists Instance + DeployRecord and returns ctx."""
    workspace = await workspace_factory()
    entity = await entity_factory(preset_slug="fox")

    record_id, ctx = await deploy_instance(
        name="test-deploy-2",
        image_version="v1.0",
        workspace_id=workspace.id,
        entity_id=entity.id,
        db=session,
    )

    assert record_id is not None
    assert ctx.instance_id is not None
    assert ctx.name.startswith("inst-")
    assert ctx.namespace == f"eyot-inst-{ctx.instance_id.replace('-', '').lower()[:20]}"
    assert ctx.cluster_id == "_gateway"
    assert ctx.image_version == "v1.0"
    assert ctx.preset_slug == "fox"
    assert ctx.env_vars["EYOT_INSTANCE_ID"] == ctx.instance_id
    assert ctx.env_vars["EYOT_POD_MODE"] == "true"
    assert "EYOT_API_URL" in ctx.env_vars

    record = await session.get(DeployRecord, record_id)
    assert record is not None
    assert record.status == DeployStatus.running.value
    assert record.action == "deploy"
    assert record.revision == 1
    assert record.image_version == "v1.0"
    assert record.instance_id == ctx.instance_id


# ── 3. execute_deploy_pipeline runs 9 steps + marks success ─────────


@pytest.mark.asyncio
async def test_execute_pipeline_runs_9_steps_mocked(
    session: AsyncSession,
    workspace_factory,
    entity_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The 9-step K8s pipeline publishes 9 SSE events + sets success."""
    workspace = await workspace_factory()
    entity = await entity_factory()

    record_id, ctx = await deploy_instance(
        name="test-deploy-3",
        image_version="v2.0",
        workspace_id=workspace.id,
        entity_id=entity.id,
        db=session,
    )
    record = await session.get(DeployRecord, record_id)
    assert record is not None and record.status == DeployStatus.running.value

    # Capture event_bus.publish calls
    publish_calls: list[tuple[str, dict]] = []

    def fake_publish(event_type: str, data: dict, event_id: str | None = None) -> None:
        publish_calls.append((event_type, data))

    monkeypatch.setattr(
        "app.services.deploy_service.event_bus",
        MagicMock(publish=fake_publish),
    )

    # Mock K8s gateway client + K8sClient surface
    fake_api_client = MagicMock(name="ApiClient")

    async def fake_get_gateway() -> MagicMock:
        return fake_api_client

    monkeypatch.setattr(
        "app.services.deploy_service.k8s_manager",
        MagicMock(get_gateway_client=fake_get_gateway),
    )

    fake_client = MagicMock(name="K8sClient")
    fake_client.ensure_namespace = AsyncMock(return_value=None)
    fake_client.create_or_skip = AsyncMock(return_value=None)
    fake_client.apply = AsyncMock(return_value=None)
    fake_client.scale_deployment = AsyncMock(return_value=None)
    fake_client.get_deployment_status = AsyncMock(
        return_value={"ready_replicas": 1},
    )
    fake_client.core = MagicMock()
    fake_client.apps = MagicMock()
    fake_client.networking = MagicMock()

    monkeypatch.setattr(
        "app.services.deploy_service.K8sClient",
        MagicMock(return_value=fake_client),
    )

    # Reroute get_session_factory()() to the test's session for step 9
    @asynccontextmanager
    async def fake_session_ctx():
        yield session

    monkeypatch.setattr(
        "app.services.deploy_service.get_session_factory",
        lambda: lambda: fake_session_ctx(),
    )

    # Run the pipeline (synchronously for the test)
    await execute_deploy_pipeline(ctx)

    # 9 steps × 2 events (running + done) = 18 publish calls
    deploy_events = [
        data for event_type, data in publish_calls if event_type == "deploy_progress"
    ]
    assert len(deploy_events) == 18

    steps_seen = {data["step"] for data in deploy_events}
    assert steps_seen == {1, 2, 3, 4, 5, 6, 7, 8, 9}

    # Each step published one "running" and one "done" event
    for step in range(1, 10):
        statuses = [
            data["status"]
            for data in deploy_events
            if data["step"] == step
        ]
        assert statuses == ["running", "done"], f"step {step} statuses={statuses}"

    # K8s API surface was actually invoked for each step
    assert fake_client.ensure_namespace.await_count == 1
    # cm + pvc + svc + np (secret + deployment use apply)
    assert fake_client.create_or_skip.await_count == 3  # pvc + svc + np
    assert fake_client.apply.await_count == 3  # cm + secret + deployment
    assert fake_client.scale_deployment.await_count == 1
    assert fake_client.get_deployment_status.await_count == 1

    # Final DB state — DeployRecord transitioned to success
    await session.refresh(record)
    assert record.status == DeployStatus.success.value
