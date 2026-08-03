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

from app.api.deps import DB, CurrentUserDep, XOrgIdHeader
from app.core.avatar_status import compute_avatar_display_status
from app.core.composer_turns import instance_has_active_turn
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
from app.core.knowledge import entry_to_dict, resolve_knowledge_for_instance
from app.core.migration_hash import compute_entity_migration_hash
from app.core.openapi import add_error_responses
from app.core.overlay import resolve_instance_agent_config
from app.core.pagination import OffsetPage, paginate_offset
from app.core.permissions import require_workspace_permission
from app.core.topology_cleanup import soft_delete_passages_touching
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
    deploy_existing_instance as svc_deploy_existing_instance,
)
from app.services.deploy_service import (
    execute_deploy_pipeline as svc_execute_deploy_pipeline,
)
from app.services.deploy_service import (
    scale_instance_runtime as svc_scale_instance_runtime,
)
from app.services.deploy_service import (
    teardown_instance_namespace as svc_teardown_instance_namespace,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/instances", tags=["Instances"])
add_error_responses(router)


def _instance_out(instance: Instance) -> InstanceOut:
    """Serialize Instance with product-facing display_status."""
    in_conversation = instance_has_active_turn(instance.id)
    return InstanceOut(
        id=instance.id,
        entity_id=instance.entity_id,
        workspace_id=instance.workspace_id,
        workspace_path=instance.workspace_path,
        status=instance.status,
        runtime_config=instance.runtime_config,
        created_at=instance.created_at,
        updated_at=instance.updated_at,
        display_status=compute_avatar_display_status(
            instance.status, in_conversation=in_conversation
        ),
        in_conversation=in_conversation,
    )


async def _refresh_instance_agent_config(db: DB, instance: Instance) -> None:
    """Resolve BaseClass ⊕ Entity overlay into ``runtime_config.agent_config``."""
    entity = await db.get(Entity, instance.entity_id)
    if entity is None or entity.deleted_at is not None:
        return
    agent_config = await resolve_instance_agent_config(db, entity)
    runtime_config = dict(instance.runtime_config or {})
    runtime_config["agent_config"] = agent_config
    instance.runtime_config = runtime_config
    instance.active_hash = await compute_entity_migration_hash(db, entity)


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
    x_organization_id: XOrgIdHeader = None,
    limit: int = 50,
    offset: int = 0,
    entity_id: str | None = None,
    workspace_id: str | None = None,
    status: str | None = None,
) -> OffsetPage[InstanceOut]:
    """Return a paginated list of active (non-deleted) instances.

    Optional filters: ``entity_id``, ``workspace_id``, ``status``.
    """
    stmt = select(Instance).where(Instance.deleted_at.is_(None))

    if entity_id is not None:
        stmt = stmt.where(Instance.entity_id == entity_id)
    if workspace_id is not None:
        await require_workspace_permission(
            db,
            current_user.user_id,
            workspace_id,
            "can_view_workspace",
            x_organization_id=x_organization_id,
        )
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
    page = await paginate_offset(db, stmt, offset, min(limit, 200))
    return OffsetPage(
        items=[_instance_out(inst) for inst in page.items],
        offset=page.offset,
        limit=page.limit,
        total=page.total,
    )


@router.get("/{instance_id}", response_model=InstanceOut)
async def get_instance(
    instance_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> InstanceOut:
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
    await require_workspace_permission(
        db,
        current_user.user_id,
        instance.workspace_id,
        "can_view_workspace",
        x_organization_id=x_organization_id,
    )
    return _instance_out(instance)


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
    x_organization_id: XOrgIdHeader = None,
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

    await require_workspace_permission(
        db,
        current_user.user_id,
        body.workspace_id,
        "can_edit_workspace",
        x_organization_id=x_organization_id,
    )

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
        active_hash=await compute_entity_migration_hash(db, entity),
    )
    db.add(instance)
    await db.flush()

    # Place the new instance on the workspace topology canvas.
    occupied = {
        (row.posx, row.posy)
        for row in (
            await db.execute(
                select(Membership.posx, Membership.posy).where(
                    Membership.workspace_id == body.workspace_id,
                    Membership.deleted_at.is_(None),
                )
            )
        ).all()
    }
    posx, posy = 0, 0
    found = False
    for row in range(40):
        for col in range(40):
            candidate = (col * 120, row * 120)
            if candidate not in occupied:
                posx, posy = candidate
                found = True
                break
        if found:
            break
    db.add(
        Membership(
            workspace_id=body.workspace_id,
            instance_id=instance.id,
            user_id=None,
            posx=posx,
            posy=posy,
        )
    )

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
            "instance.already_exists",
            "errors.instance.already_exists",
            "Instance path taken or entity already introduced in this workspace",
        )
    await db.refresh(instance)
    return instance


@router.patch("/{instance_id}", response_model=InstanceOut)
async def update_instance(
    instance_id: str,
    body: InstanceUpdate,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
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

    await require_workspace_permission(
        db,
        current_user.user_id,
        instance.workspace_id,
        "can_edit_workspace",
        x_organization_id=x_organization_id,
    )

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
    x_organization_id: XOrgIdHeader = None,
) -> None:
    """Soft-delete an instance.

    If the instance is ``running``, it is stopped first (DB + best-effort K8s
    scale-down). Portal should confirm before calling. Idempotent when already
    ``deleting``.
    """
    instance = await db.get(Instance, instance_id)
    if instance is None or instance.deleted_at is not None:
        raise NotFoundError(
            "instance.not_found",
            "errors.instance.not_found",
            f"Instance '{instance_id}' not found",
        )

    await require_workspace_permission(
        db,
        current_user.user_id,
        instance.workspace_id,
        "can_edit_workspace",
        x_organization_id=x_organization_id,
    )

    if instance.status == InstanceStatus.deleting.value:
        return

    if instance.status == InstanceStatus.running.value:
        instance.status = InstanceStatus.pending.value
        await svc_scale_instance_runtime(instance_id, 0)

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
    mem_ids = (
        await db.execute(
            select(Membership.id).where(
                Membership.instance_id == instance.id,
                Membership.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    await db.execute(
        update(Membership)
        .where(
            Membership.instance_id == instance.id,
            Membership.deleted_at.is_(None),
        )
        .values(deleted_at=func.now())
    )
    await soft_delete_passages_touching(db, list(mem_ids))
    instance.soft_delete()
    await db.commit()

    await svc_teardown_instance_namespace(instance_id)


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
    x_organization_id: XOrgIdHeader = None,
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

    await require_workspace_permission(
        db,
        current_user.user_id,
        instance.workspace_id,
        "can_edit_workspace",
        x_organization_id=x_organization_id,
    )

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
    x_organization_id: XOrgIdHeader = None,
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
        await require_workspace_permission(
            db,
            current_user.user_id,
            instance.workspace_id,
            "can_edit_workspace",
            x_organization_id=x_organization_id,
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
            x_organization_id=x_organization_id,
        )

    instance = await db.get(Instance, instance_id)
    if instance is None or instance.deleted_at is not None:
        raise NotFoundError(
            "instance.not_found",
            "errors.instance.not_found",
            f"Instance '{instance_id}' not found",
        )

    await require_workspace_permission(
        db,
        current_user.user_id,
        instance.workspace_id,
        "can_edit_workspace",
        x_organization_id=x_organization_id,
    )

    await _refresh_instance_agent_config(db, instance)

    record_id, ctx = await svc_deploy_existing_instance(
        instance_id,
        image_version="latest",
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
    x_organization_id: XOrgIdHeader = None,
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
        x_organization_id=x_organization_id,
    )


@router.post("/{instance_id}/restart", response_model=RestartResultOut)
async def restart_instance(
    instance_id: str,
    body: RestartRequest,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> RestartResultOut:
    """Re-sync / recycle an instance (stop → re-deploy).

    Confirmed by Portal. Running instances are stopped (scaled to 0), hash
    refreshed, then a new deploy pipeline is started. ``force`` is accepted
    for backward compatibility but no longer required.
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

    await require_workspace_permission(
        db,
        current_user.user_id,
        instance.workspace_id,
        "can_operate_workspace",
        x_organization_id=x_organization_id,
    )

    was_running = instance.status == InstanceStatus.running.value
    if was_running:
        await svc_scale_instance_runtime(instance_id, 0)

    old_hash = instance.active_hash
    instance.status = InstanceStatus.restarting.value
    await db.flush()

    instance.active_hash = entity.migration_hash
    instance.status = InstanceStatus.deploying.value

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
            "force": body.force or was_running,
        },
        session=db,
    )
    await db.commit()

    try:
        record_id, ctx = await svc_deploy_existing_instance(
            instance_id,
            triggered_by=current_user.user_id,
            db=db,
        )
        asyncio.create_task(
            svc_execute_deploy_pipeline(ctx),
            name=f"restart-deploy-{instance_id[:8]}",
        )
        logger.info(
            "restart triggered deploy record_id=%s instance_id=%s",
            record_id,
            instance_id,
        )
    except Exception:  # noqa: BLE001
        logger.exception("restart deploy failed instance_id=%s", instance_id)
        instance = await db.get(Instance, instance_id)
        if instance is not None:
            instance.status = InstanceStatus.failed.value
            await db.commit()

    instance = await db.get(Instance, instance_id)
    return RestartResultOut(
        restarted_at=datetime.now(timezone.utc).isoformat(),
        instance_id=instance_id,
        old_hash=old_hash,
        new_hash=instance.active_hash if instance else None,
        status_after=instance.status if instance else InstanceStatus.failed.value,
    )


@router.post("/batch-restart", response_model=BatchRestartResultOut)
async def batch_restart_instances(
    body: BatchRestartRequest,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
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
    await require_workspace_permission(
        db,
        current_user.user_id,
        first_workspace,
        "can_operate_workspace",
        x_organization_id=x_organization_id,
    )

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


@router.get("/{instance_id}/tunnel-status")
async def instance_tunnel_status(
    instance_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> dict[str, object]:
    """Report whether the Instance Host is connected on the Tunnel hub."""
    result = await db.execute(
        select(Instance).where(Instance.id == instance_id, Instance.deleted_at.is_(None))
    )
    inst = result.scalar_one_or_none()
    if inst is None:
        raise NotFoundError(
            "instance.not_found",
            "errors.instance.not_found",
            f"Instance '{instance_id}' not found",
        )
    await require_workspace_permission(
        db,
        current_user.user_id,
        inst.workspace_id,
        "can_view_workspace",
        x_organization_id=x_organization_id,
    )
    from app.services.tunnel.tunnel_hub import tunnel_hub

    connected = tunnel_hub.is_connected(instance_id)
    return {"instance_id": instance_id, "connected": connected}


@router.get("/{instance_id}/knowledge/resolved")
async def resolve_instance_knowledge(
    instance_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> dict[str, object]:
    """Resolve the knowledge visible to an instance (v4.2 D16/H1).

    Scope chain: instance → entity → namespace → org. Rows are filtered by
    scope ownership visibility + binding, then merged per key so at most one
    item survives: workspace > namespace > org > system, same-scope tie by
    ``updated_at`` DESC then ``id`` DESC.
    """
    inst = await db.get(Instance, instance_id)
    if inst is None or inst.deleted_at is not None:
        raise NotFoundError(
            "instance.not_found",
            "errors.instance.not_found",
            f"Instance '{instance_id}' not found",
        )
    await require_workspace_permission(
        db,
        current_user.user_id,
        inst.workspace_id,
        "can_view_workspace",
        x_organization_id=x_organization_id,
    )
    resolved = await resolve_knowledge_for_instance(db, inst)
    return {"items": [entry_to_dict(row) for row in resolved]}


@router.post("/{instance_id}/stop", response_model=InstanceOut)
async def stop_instance(
    instance_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> Instance:
    """Stop the Instance runtime (scale to 0) and mark ``pending``.

    Allowed from: ``running``. Emits ``instance.stopped``.
    """
    inst = await _transition(
        instance_id,
        allowed=[InstanceStatus.running.value],
        new_status=InstanceStatus.pending.value,
        event_type=INSTANCE_STOPPED,
        db=db,
        current_user=current_user,
        x_organization_id=x_organization_id,
    )
    await svc_scale_instance_runtime(instance_id, 0)
    return inst


@router.post("/{instance_id}/fail", response_model=InstanceOut)
async def fail_instance(
    instance_id: str,
    body: FailBody,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> InstanceOut:
    """Transition instance to ``failed`` (keep topology seat for retry / connect).

    Allowed from any current status. The ``reason`` is recorded in the
    emitted event payload. Does **not** soft-delete the membership — operators
    need the node on canvas to reconnect or redeploy.
    """
    inst = await _transition(
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
        x_organization_id=x_organization_id,
        payload={"reason": body.reason},
    )
    return _instance_out(inst)
