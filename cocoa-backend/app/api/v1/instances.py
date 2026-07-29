"""Instance API routes — CRUD + lifecycle state machine action endpoints.

P7 implements the full Instance lifecycle: create → deploy → start →
restart → stop → fail → delete. Each state transition is governed by
an explicit allowed-status whitelist; invalid transitions return 409.

P8 harness control commands (interrupt / pause / resume / status /
snapshot) live in :mod:`app.api.v1.harness` — this module hosts only
the P7 CRUD + lifecycle surface so it stays under the 250 LOC ceiling.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, status
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, CurrentUserDep
from app.core.errors import ConflictError, NotFoundError
from app.core.event_types import (
    INSTANCE_BATCH_RESTARTED,
    INSTANCE_CREATED,
    INSTANCE_DELETED,
    INSTANCE_DEPLOYED,
    INSTANCE_FAILED,
    INSTANCE_RESTARTED,
    INSTANCE_STARTED,
    INSTANCE_STOPPED,
)
from app.core.events import emit
from app.core.migration_hash import compute_entity_migration_hash
from app.core.openapi import add_error_responses
from app.core.overlay import resolve_instance_agent_config
from app.core.pagination import OffsetPage, paginate_offset
from app.core.permissions import require_workspace_role
from app.core.workspace import generate_workspace_path
from app.models.entity import Entity
from app.models.instance import Instance, InstanceStatus
from app.models.workspace import Membership, Workspace
from app.schemas.instance import (
    InstanceCreate,
    InstanceOut,
    InstanceOutWithToken,
    InstanceUpdate,
)
from app.schemas.instance_actions import (
    BatchRestartRequest,
    BatchRestartResultOut,
    RestartRequest,
    RestartResultOut,
)
from app.services.deploy_service import (
    deploy_instance as svc_deploy_instance,
)
from app.services.deploy_service import (
    execute_deploy_pipeline as svc_execute_deploy_pipeline,
)
from app.services.k8s.client_manager import k8s_manager
from app.services.k8s.k8s_client import K8sClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/instances", tags=["Instances"])
add_error_responses(router)


async def _refresh_instance_agent_config(db: DB, instance: Instance) -> None:
    """Resolve BaseClass ⊕ Entity overlay into ``runtime_config.agent_config``."""
    entity = await db.get(Entity, instance.entity_id)
    if entity is None or entity.deleted_at is not None:
        return
    agent_config = await resolve_instance_agent_config(db, entity)
    runtime_config = dict(instance.runtime_config or {})
    runtime_config["agent_config"] = agent_config
    instance.runtime_config = runtime_config
    instance.active_hash = compute_entity_migration_hash(entity)


class FailBody(BaseModel):
    """Payload for ``POST /instances/{instance_id}/fail``."""

    reason: str


class DeployRecordOut(BaseModel):
    """Response body for ``POST /instances/{instance_id}/deploy`` (P11c).

    Mirrors the public fields of :class:`app.models.deploy_record.DeployRecord`
    the API caller needs to track the asynchronous K8s pipeline run.
    Defined locally to avoid coupling this module to ``app.schemas``.
    """

    id: str
    instance_id: str
    revision: int = 1
    action: str
    status: str
    image_version: str | None = None


def _is_k8s_available() -> bool:
    """P11c: probe whether a K8s cluster is reachable from this process.

    In local mode (no cluster, no ``KUBECONFIG``, no service-account
    token, or ``COCOA_K8S_DISABLED=true``), returns ``False`` so the
    deploy endpoint can short-circuit with 503 instead of crashing.
    """

    if os.environ.get("COCOA_K8S_DISABLED", "").lower() == "true":
        return False
    return (
        os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount/token")
        or os.environ.get("KUBECONFIG") is not None
        or os.environ.get("GATEWAY_KUBECONFIG") is not None
    )


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=OffsetPage[InstanceOut])
async def list_instances(
    db: DB,
    current_user: CurrentUserDep,
    limit: int = 50,
    offset: int = 0,
    entity_id: str | None = None,
    workspace_id: str | None = None,
    status: str | None = None,
) -> OffsetPage:
    """Return a paginated list of active (non-deleted) instances.

    Optional filters: ``entity_id``, ``workspace_id``, ``status``.
    """
    stmt = select(Instance).where(Instance.deleted_at.is_(None))

    if entity_id is not None:
        stmt = stmt.where(Instance.entity_id == entity_id)
    if workspace_id is not None:
        await require_workspace_role(db, current_user.user_id, workspace_id, "viewer")
        stmt = stmt.where(Instance.workspace_id == workspace_id)
    else:
        stmt = stmt.where(
            Instance.workspace_id.in_(
                select(Membership.workspace_id).where(
                    Membership.user_id == current_user.user_id,
                    Membership.deleted_at.is_(None),
                )
            )
        )
    if status is not None:
        stmt = stmt.where(Instance.status == status)

    stmt = stmt.order_by(Instance.created_at)
    return await paginate_offset(db, stmt, offset, min(limit, 200))


@router.get("/{instance_id}", response_model=InstanceOut)
async def get_instance(
    instance_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> Instance:
    """Return a single instance by ID.

    Raises 404 if the instance does not exist or has been soft-deleted.
    """
    instance = await db.get(Instance, instance_id)
    if instance is None or instance.deleted_at is not None:
        raise NotFoundError(
            "instance.not_found",
            "errors.instance.not_found",
            f"Instance '{instance_id}' not found",
        )
    await require_workspace_role(db, current_user.user_id, instance.workspace_id, "editor")
    return instance


# ---------------------------------------------------------------------------
# Create / Update / Delete
# ---------------------------------------------------------------------------


@router.post(
    "", response_model=InstanceOutWithToken, status_code=status.HTTP_201_CREATED
)
async def create_instance(
    body: InstanceCreate,
    db: DB,
    current_user: CurrentUserDep,
) -> Instance:
    """Create a new instance.

    Validates that the referenced entity and workspace exist (404 if not).
    The caller must hold at least the ``editor`` role in the target workspace.
    If ``workspace_path`` is omitted, one is generated automatically.
    A ``proxy_token`` is created automatically for P8 harness authentication.
    The initial status is ``creating``.
    """
    entity = await db.get(Entity, body.entity_id)
    if entity is None or entity.deleted_at is not None:
        raise NotFoundError(
            "entity.not_found",
            "errors.entity.not_found",
            f"Entity '{body.entity_id}' not found",
        )

    workspace = await db.get(Workspace, body.workspace_id)
    if workspace is None or workspace.deleted_at is not None:
        raise NotFoundError(
            "workspace.not_found",
            "errors.workspace.not_found",
            f"Workspace '{body.workspace_id}' not found",
        )

    await require_workspace_role(db, current_user.user_id, body.workspace_id, "editor")

    workspace_path = body.workspace_path or generate_workspace_path(
        entity.slug, str(uuid4())
    )

    agent_config = await resolve_instance_agent_config(db, entity)
    runtime_config = dict(body.runtime_config or {})
    runtime_config["agent_config"] = agent_config

    instance = Instance(
        entity_id=body.entity_id,
        workspace_id=body.workspace_id,
        workspace_path=workspace_path,
        status=InstanceStatus.creating.value,
        runtime_config=runtime_config,
        proxy_token=str(uuid4()),
        active_hash=compute_entity_migration_hash(entity),
    )
    db.add(instance)
    await emit(
        INSTANCE_CREATED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="instance",
        resource_id=instance.id,
        payload={"workspace_path": workspace_path, "workspace_id": body.workspace_id},
        session=db,
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError(
            "instance.workspace_path_taken",
            "errors.instance.workspace_path_taken",
            f"workspace_path '{workspace_path}' is already used by another instance",
        )
    await db.refresh(instance)
    return instance


@router.patch("/{instance_id}", response_model=InstanceOut)
async def update_instance(
    instance_id: str,
    body: InstanceUpdate,
    db: DB,
    current_user: CurrentUserDep,
) -> Instance:
    """Update an existing instance.

    Only ``runtime_config`` and ``workspace_path`` are mutable. Changes to
    ``status`` must go through dedicated action endpoints.
    Raises 404 if the instance does not exist.
    """
    instance = await db.get(Instance, instance_id)
    if instance is None or instance.deleted_at is not None:
        raise NotFoundError(
            "instance.not_found",
            "errors.instance.not_found",
            f"Instance '{instance_id}' not found",
        )

    await require_workspace_role(db, current_user.user_id, instance.workspace_id, "editor")

    patch_data = body.model_dump(exclude_unset=True)
    for field, value in patch_data.items():
        setattr(instance, field, value)

    workspace_path = instance.workspace_path
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError(
            "instance.workspace_path_taken",
            "errors.instance.workspace_path_taken",
            f"workspace_path '{workspace_path}' is already used by another instance",
        )
    await db.refresh(instance)
    return instance


@router.delete("/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_instance(
    instance_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> None:
    """Soft-delete an instance.

    The instance must not be ``running`` — stop it first via
    ``POST /instances/{instance_id}/stop``. If the instance is already
    ``deleting`` the call is idempotent and returns 204.
    Raises 404 if the instance does not exist.
    """
    instance = await db.get(Instance, instance_id)
    if instance is None or instance.deleted_at is not None:
        raise NotFoundError(
            "instance.not_found",
            "errors.instance.not_found",
            f"Instance '{instance_id}' not found",
        )

    await require_workspace_role(db, current_user.user_id, instance.workspace_id, "editor")

    if instance.status == InstanceStatus.deleting.value:
        return

    if instance.status == InstanceStatus.running.value:
        raise ConflictError(
            "instance.still_running",
            "errors.instance.still_running",
            f"Instance '{instance_id}' is still running — stop it first",
        )

    previous_status = instance.status
    instance.status = InstanceStatus.deleting.value
    await emit(
        INSTANCE_DELETED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="instance",
        resource_id=instance.id,
        payload={"previous_status": previous_status},
        session=db,
    )
    await db.execute(
        update(Membership)
        .where(
            Membership.instance_id == instance.id,
            Membership.deleted_at.is_(None),
        )
        .values(deleted_at=func.now())
    )
    instance.soft_delete()
    await db.commit()

    # P11c: best-effort K8s namespace teardown. The DB soft-delete is the
    # authoritative source of truth — a missing or unreachable cluster
    # must never block the API call, so any error is logged and swallowed.
    namespace = f"cocoa-default-{instance.workspace_path or instance.id}"
    try:
        api_client = await k8s_manager.get_gateway_client()
        client = K8sClient(api_client)
        await client.core.delete_namespace(namespace)
    except Exception as exc:  # noqa: BLE001 — best-effort teardown
        logger.warning(
            "K8s namespace delete failed (continuing)",
            extra={"namespace": namespace, "error": str(exc)},
        )


# ---------------------------------------------------------------------------
# Lifecycle action endpoints (R4 Stripe-style POST /{id}/action)
# ---------------------------------------------------------------------------


async def _transition(
    instance_id: str,
    allowed: list[str],
    new_status: str,
    event_type: str | None,
    db,
    current_user: CurrentUserDep,
    *,
    payload: dict | None = None,
) -> Instance:
    """Shared state-machine transition helper.

    Selects the instance row with ``FOR UPDATE``, validates the current
    status against *allowed*, sets *new_status*, emits *event_type*
    (unless ``None``), commits, and returns the refreshed instance.
    """
    result = await db.execute(
        select(Instance)
        .where(Instance.id == instance_id, Instance.deleted_at.is_(None))
        .with_for_update()
    )
    instance = result.scalar_one_or_none()
    if instance is None:
        raise NotFoundError(
            "instance.not_found",
            "errors.instance.not_found",
            f"Instance '{instance_id}' not found",
        )

    await require_workspace_role(db, current_user.user_id, instance.workspace_id, "editor")

    if instance.status not in allowed:
        raise ConflictError(
            "instance.invalid_transition",
            "errors.instance.invalid_transition",
            f"Cannot transition from '{instance.status}' to '{new_status}'",
            details={"current": instance.status, "allowed": allowed},
        )

    instance.status = new_status

    if event_type is not None:
        await emit(
            event_type,
            actor_type="user",
            actor_id=current_user.user_id,
            resource_type="instance",
            resource_id=instance.id,
            payload=payload or {},
            session=db,
        )

    await db.commit()
    await db.refresh(instance)
    return instance


@router.post("/{instance_id}/deploy")
async def deploy_instance(
    instance_id: str,
    db: DB,
    current_user: CurrentUserDep,
):
    """Deploy an instance — P7 contract with P11c K8s upgrade.

    When a K8s cluster is reachable, kicks off the 9-step
    :func:`app.services.deploy_service.deploy_instance` pipeline; a
    :class:`DeployRecord` is returned synchronously and the rest of the
    pipeline runs as a fire-and-forget ``asyncio`` task streamed via
    the SSE endpoint (``GET /api/v1/deploy/deploy-progress/{record_id}``).

    When no K8s cluster is reachable (local dev, no kubeconfig, or
    ``COCOA_K8S_DISABLED=true``), falls back to P7's in-process DB
    state transition so the legacy P7 contract (``status='deploying'``,
    ``INSTANCE_DEPLOYED`` event, ``InstanceOut`` response) keeps
    working without a cluster.
    """
    if not _is_k8s_available():
        instance = await db.get(Instance, instance_id)
        if instance is None or instance.deleted_at is not None:
            raise NotFoundError(
                "instance.not_found",
                "errors.instance.not_found",
                f"Instance '{instance_id}' not found",
            )
        await require_workspace_role(
            db, current_user.user_id, instance.workspace_id, "editor"
        )
        await _refresh_instance_agent_config(db, instance)
        await db.flush()
        # P7 fallback: in-process DB transition (no K8s cluster reachable).
        return await _transition(
            instance_id,
            allowed=[
                InstanceStatus.creating.value,
                InstanceStatus.restarting.value,
            ],
            new_status=InstanceStatus.deploying.value,
            event_type=INSTANCE_DEPLOYED,
            db=db,
            current_user=current_user,
        )

    instance = await db.get(Instance, instance_id)
    if instance is None or instance.deleted_at is not None:
        raise NotFoundError(
            "instance.not_found",
            "errors.instance.not_found",
            f"Instance '{instance_id}' not found",
        )

    await require_workspace_role(db, current_user.user_id, instance.workspace_id, "editor")

    await _refresh_instance_agent_config(db, instance)

    record_id, ctx = await svc_deploy_instance(
        name=instance.workspace_path or str(instance.id),
        image_version="latest",
        workspace_id=instance.workspace_id,
        entity_id=instance.entity_id,
        proxy_token=instance.proxy_token or "",
        triggered_by=current_user.user_id,
        db=db,
    )

    asyncio.create_task(svc_execute_deploy_pipeline(ctx))

    return DeployRecordOut(
        id=record_id,
        instance_id=instance_id,
        revision=getattr(ctx, "revision", 1),
        action="deploy",
        status="running",
        image_version=ctx.image_version,
    )


@router.post("/{instance_id}/start", response_model=InstanceOut)
async def start_instance(
    instance_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> Instance:
    """Transition instance from pending/deploying to running (P7 contract).

    Per P11c plan: start is a state machine action, NOT a deploy. K8s deploy
    happens via POST /instances/{id}/deploy which now falls back to P7 in
    non-K8s mode. start_instance remains a pure state-machine action.
    """
    return await _transition(
        instance_id,
        allowed=[InstanceStatus.pending.value, InstanceStatus.deploying.value],
        new_status=InstanceStatus.running.value,
        event_type=INSTANCE_STARTED,
        db=db,
        current_user=current_user,
    )


@router.post("/{instance_id}/restart", response_model=RestartResultOut)
async def restart_instance(
    instance_id: str,
    body: RestartRequest,
    db: DB,
    current_user: CurrentUserDep,
) -> RestartResultOut:
    """Re-sync an outdated instance to the current Entity.migration_hash.

    Per PRD §13.6.7: this is the operator flow that runs after a
    promote (when the live-status shows the instance is outdated). The
    instance is moved ``restarting`` → ``pending`` and its
    ``active_hash`` is reset to the current Entity.migration_hash.

    Refuses with 409 if ``status == "running"`` and ``force=false``.
    The K8s pickup hook is out of scope for this wave (P11c).
    """
    instance = await db.get(Instance, instance_id)
    if instance is None or instance.deleted_at is not None:
        raise NotFoundError(
            "instance.not_found",
            "errors.instance.not_found",
            f"Instance '{instance_id}' not found",
        )

    entity = await db.get(Entity, instance.entity_id)
    if entity is None or entity.deleted_at is not None:
        raise NotFoundError(
            "entity.not_found",
            "errors.entity.not_found",
            f"Entity '{instance.entity_id}' not found",
        )

    await require_workspace_role(db, current_user.user_id, instance.workspace_id, "operator")

    if instance.status == InstanceStatus.running.value and not body.force:
        raise ConflictError(
            "instance.running",
            "errors.instance.running",
            f"Instance '{instance_id}' is running; pass force=true to override",
            details={
                "running_instance_id": instance_id,
                "current_status": instance.status,
            },
        )

    old_hash = instance.active_hash
    instance.status = InstanceStatus.restarting.value
    await db.flush()

    instance.active_hash = entity.migration_hash
    instance.status = InstanceStatus.pending.value

    await emit(
        INSTANCE_RESTARTED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="instance",
        resource_id=instance.id,
        payload={
            "old_hash": old_hash,
            "new_hash": instance.active_hash,
            "reason": body.reason,
            "force": body.force,
        },
        session=db,
    )
    await db.commit()

    return RestartResultOut(
        restarted_at=datetime.now(timezone.utc).isoformat(),
        instance_id=instance_id,
        old_hash=old_hash,
        new_hash=instance.active_hash,
        status_after=instance.status,
    )


@router.post("/batch-restart", response_model=BatchRestartResultOut)
async def batch_restart_instances(
    body: BatchRestartRequest,
    db: DB,
    current_user: CurrentUserDep,
) -> BatchRestartResultOut:
    """Bulk re-sync for T4 — picks up every outdated instance in one call.

    Per PRD §13.6.7: refuse the entire batch if any instance is running
    (returns 409 with the offending IDs in ``details``). Otherwise set
    ``active_hash = Entity.migration_hash`` and ``status = restarting``
    for each instance.
    """
    # 1. Load all instances.
    instances_q = await db.execute(
        select(Instance).where(
            Instance.id.in_(body.instance_ids),
            Instance.deleted_at.is_(None),
        )
    )
    instances = list(instances_q.scalars().all())
    found_ids = {i.id for i in instances}
    missing = [iid for iid in body.instance_ids if iid not in found_ids]
    if missing:
        raise NotFoundError(
            "instance.not_found",
            "errors.instance.not_found",
            f"Instance(s) not found: {missing}",
            details={"missing_instance_ids": missing},
        )

    # 2. Auth: operator role in the first instance's workspace (the batch
    # is implicitly same-workspace — if not, the permission check fails).
    first_workspace = instances[0].workspace_id
    await require_workspace_role(db, current_user.user_id, first_workspace, "operator")

    # 3. Reject batch if any instance is running.
    running = [i.id for i in instances if i.status == InstanceStatus.running.value]
    if running:
        raise ConflictError(
            "instance.batch_has_running",
            "errors.instance.batch_has_running",
            "Batch contains running instances; stop them first",
            details={"running_instance_ids": running},
        )

    # 4. Re-sync each instance.
    restarted_ids: list[str] = []
    skipped: list[str] = []
    entity_cache: dict[str, Entity] = {}
    for inst in instances:
        emp = entity_cache.get(inst.entity_id)
        if emp is None:
            emp = await db.get(Entity, inst.entity_id)
            if emp is None:
                skipped.append(inst.id)
                continue
            entity_cache[inst.entity_id] = emp
            # Check workspace-equivalence while we have the workspace.
            if emp.deleted_at is not None:
                skipped.append(inst.id)
                continue
        inst.active_hash = emp.migration_hash
        inst.status = InstanceStatus.restarting.value
        restarted_ids.append(inst.id)

    await emit(
        INSTANCE_BATCH_RESTARTED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="instance",
        resource_id=None,
        payload={
            "instance_ids": body.instance_ids,
            "reason": body.reason,
            "restarted_count": len(restarted_ids),
        },
        session=db,
    )

    await db.commit()

    return BatchRestartResultOut(
        restarted_count=len(restarted_ids),
        restarted_at=datetime.now(timezone.utc).isoformat(),
        instance_ids=restarted_ids,
        skipped=skipped,
    )


@router.post("/{instance_id}/stop", response_model=InstanceOut)
async def stop_instance(
    instance_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> Instance:
    """Transition instance to ``pending`` (graceful shutdown).

    Allowed from: ``running``. Emits an ``instance.stopped`` lifecycle event.
    """
    return await _transition(
        instance_id,
        allowed=[InstanceStatus.running.value],
        new_status=InstanceStatus.pending.value,
        event_type=INSTANCE_STOPPED,
        db=db,
        current_user=current_user,
    )


@router.post("/{instance_id}/fail", response_model=InstanceOut)
async def fail_instance(
    instance_id: str,
    body: FailBody,
    db: DB,
    current_user: CurrentUserDep,
) -> Instance:
    """Transition instance to ``failed``.

    Allowed from any current status. The ``reason`` is recorded in the
    emitted event payload.
    """
    return await _transition(
        instance_id,
        allowed=[
            InstanceStatus.creating.value,
            InstanceStatus.pending.value,
            InstanceStatus.deploying.value,
            InstanceStatus.running.value,
            InstanceStatus.restarting.value,
            InstanceStatus.failed.value,
            InstanceStatus.deleting.value,
        ],
        new_status=InstanceStatus.failed.value,
        event_type=INSTANCE_FAILED,
        db=db,
        current_user=current_user,
        payload={"reason": body.reason},
    )
