"""P11c Todo 10: ``COCOA_PROXY_TOKEN`` reaches the K8s deployment env and
the ``HARNESS_CHECKPOINT`` payload untouched.

Two tests pin the seam:

1. ``test_proxy_token_in_deployment_env`` — :func:`deploy_service.deploy_instance`
   places ``proxy_token`` into ``ctx.env_vars["COCOA_PROXY_TOKEN"]`` so the
   ``build_env_secret`` step in the K8s pipeline can hand the token to the
   agent pod.
2. ``test_proxy_token_in_emit_payload`` — the supervisor's
   ``_on_harness_event`` does not validate or strip ``proxy_token`` from the
   ``HARNESS_CHECKPOINT`` payload (the seam the K8s-mode runtime relies on
   to attribute checkpoints to the correct Instance).
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.event_types import HARNESS_CHECKPOINT
from app.core.events import emit
from app.core.harness_supervisor import supervisor
from app.models.deploy_record import DeployRecord
from app.services.deploy_service import deploy_instance

# ── shared fixtures ────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def wired_factory(db_url: str):  # noqa: ARG001
    """Bind :func:`get_session_factory` to the per-test DB before invoking emit()."""
    import app.core.config as cfg
    import app.core.db as db_mod

    previous_url = cfg.settings.DATABASE_URL
    cfg.settings.DATABASE_URL = db_url
    db_mod._engine = None
    db_mod._session_factory = None
    try:
        yield
    finally:
        db_mod._engine = None
        db_mod._session_factory = None
        cfg.settings.DATABASE_URL = previous_url


# ── 1. COCOA_PROXY_TOKEN injected into the K8s env ────────────────────────


@pytest.mark.asyncio
async def test_proxy_token_in_deployment_env(
    session, workspace_factory, entity_factory,
) -> None:
    """``deploy_instance`` puts ``proxy_token`` into ``ctx.env_vars``."""
    workspace = await workspace_factory()
    entity = await entity_factory()
    proxy_token = "deadbeef-1234-5678-9abc-def012345678"

    record_id, ctx = await deploy_instance(
        name="proxy-token-instance",
        image_version="v1.0",
        workspace_id=workspace.id,
        entity_id=entity.id,
        proxy_token=proxy_token,
        db=session,
    )

    assert record_id is not None
    assert ctx.env_vars["COCOA_PROXY_TOKEN"] == proxy_token
    assert ctx.env_vars["COCOA_PROXY_TOKEN"] != "", (
        "COCOA_PROXY_TOKEN must not be empty after injection"
    )

    record = await session.get(DeployRecord, record_id)
    assert record is not None


# ── 2. proxy_token survives the HARNESS_CHECKPOINT dispatch ────────────────


@pytest.mark.asyncio
async def test_proxy_token_in_emit_payload(
    wired_factory,  # noqa: ARG001
    session, instance_factory, workspace_factory, entity_factory, loop_state_factory,
) -> None:
    """Supervisor ``_on_harness_event`` keeps ``proxy_token`` in the payload."""
    await supervisor.start()
    workspace = await workspace_factory()
    entity = await entity_factory()
    instance = await instance_factory(
        entity_id=entity.id, workspace_id=workspace.id,
    )

    from app.models.workspace import Membership
    session.add(
        Membership(
            workspace_id=workspace.id, instance_id=instance.id,
            posx=0, posy=0, role="member",
        )
    )
    await loop_state_factory(instance)
    await session.commit()

    proxy_token = "k8s-attribute-token-cafe"
    await emit(
        HARNESS_CHECKPOINT,
        actor_type="instance", actor_id=instance.id,
        resource_type="instance", resource_id=instance.id,
        payload={
            "token_estimate": 0,
            "iteration": 0,
            "instance_id": instance.id,
            "proxy_token": proxy_token,
        },
        session=session,
    )
    await session.commit()

    from app.models.event import Event

    rows = (
        await session.execute(
            select(Event).where(
                Event.type == HARNESS_CHECKPOINT,
                Event.resource_id == instance.id,
            )
        )
    ).scalars().all()
    assert rows, "HARNESS_CHECKPOINT must persist into the events table"
    persisted = rows[-1].payload or {}
    assert persisted.get("proxy_token") == proxy_token, (
        "supervisor must not strip proxy_token from the payload"
    )
