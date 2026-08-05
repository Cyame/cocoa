"""Reusable instance restart pipeline (v4.9.1 Wave 3).

Extracted from ``app/api/v1/instances.py::restart_instance`` so the
workspace cerebellum restart endpoint can drive the same scale-to-zero →
hash-sync → re-deploy semantics without a route-to-route nested call.

Pipeline semantics (kept byte-for-byte compatible with the original
``restart_instance`` handler):

1. Scale a running instance's K8s runtime to 0 (best-effort).
2. Persist ``restarting`` → sync ``active_hash`` to ``entity.migration_hash``
   → persist ``deploying``.
3. Emit the ``instance.restarted`` audit event (actor = user).
4. Kick off a real deploy: ``deploy_existing_instance`` creates a
   ``DeployRecord``, then ``execute_deploy_pipeline`` runs as a background
   asyncio task.
5. If the deploy kick-off raises, the instance is marked ``failed``.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_types import INSTANCE_RESTARTED
from app.core.events import emit
from app.models.entity import Entity
from app.models.instance import Instance, InstanceStatus
from app.services.deploy_service import (
    deploy_existing_instance as svc_deploy_existing_instance,
)
from app.services.deploy_service import (
    execute_deploy_pipeline as svc_execute_deploy_pipeline,
)
from app.services.deploy_service import (
    scale_instance_runtime as svc_scale_instance_runtime,
)

logger = logging.getLogger(__name__)


@dataclass
class RestartOutcome:
    """Result of the restart pipeline, mirroring ``RestartResultOut`` fields."""

    old_hash: str | None
    new_hash: str | None
    status_after: str
    restarted_at: str
    record_id: str | None = None
    deploy_started: bool = False


async def restart_instance_runtime(
    db: AsyncSession,
    *,
    instance: Instance,
    entity: Entity,
    triggered_by: str,
    reason: str | None = None,
    force: bool = False,
) -> RestartOutcome:
    """Re-sync / recycle an instance (stop → re-deploy).

    The caller is responsible for the instance/entity lookup and the
    permission check. Running instances are stopped (scaled to 0),
    ``active_hash`` is synced to ``entity.migration_hash``, an
    ``instance.restarted`` audit event is emitted, then a new deploy
    pipeline is started. If the deploy kick-off raises, the instance is
    marked ``failed``.
    """
    was_running = instance.status == InstanceStatus.running.value
    if was_running:
        await svc_scale_instance_runtime(instance.id, 0)

    old_hash = instance.active_hash
    instance.status = InstanceStatus.restarting.value
    await db.flush()

    instance.active_hash = entity.migration_hash
    instance.status = InstanceStatus.deploying.value

    await emit(
        INSTANCE_RESTARTED,
        actor_type="user",
        actor_id=triggered_by,
        resource_type="instance",
        resource_id=instance.id,
        payload={
            "old_hash": old_hash,
            "new_hash": instance.active_hash,
            "reason": reason,
            "force": force or was_running,
        },
        session=db,
    )
    await db.commit()

    record_id: str | None = None
    deploy_started = False
    try:
        record_id, ctx = await svc_deploy_existing_instance(
            instance.id,
            triggered_by=triggered_by,
            db=db,
        )
        asyncio.create_task(
            svc_execute_deploy_pipeline(ctx),
            name=f"restart-deploy-{instance.id[:8]}",
        )
        deploy_started = True
        logger.info(
            "restart triggered deploy record_id=%s instance_id=%s",
            record_id,
            instance.id,
        )
    except Exception:  # noqa: BLE001
        logger.exception("restart deploy failed instance_id=%s", instance.id)
        instance = await db.get(Instance, instance.id)
        if instance is not None:
            instance.status = InstanceStatus.failed.value
            await db.commit()

    instance = await db.get(Instance, instance.id)
    return RestartOutcome(
        old_hash=old_hash,
        new_hash=instance.active_hash if instance else None,
        status_after=instance.status if instance else InstanceStatus.failed.value,
        restarted_at=datetime.now(timezone.utc).isoformat(),
        record_id=record_id,
        deploy_started=deploy_started,
    )
