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
    INSTANCE_DELETED,
    INSTANCE_DEPLOYED,
    INSTANCE_FAILED,
    INSTANCE_KNOWLEDGE_INCONSISTENT,
    INSTANCE_STARTED,
    INSTANCE_STOPPED,
)
from app.core.events import emit
from app.core.inject_queue import enqueue_inject
from app.core.knowledge import entry_to_dict, resolve_knowledge_for_instance
from app.core.knowledge_spawn import check_knowledge_consistency
from app.core.migration_hash import compute_entity_migration_hash
from app.core.openapi import add_error_responses
from app.core.overlay import resolve_instance_agent_config
from app.core.pagination import OffsetPage, paginate_offset
from app.core.permissions import require_workspace_permission
from app.core.topology_cleanup import soft_delete_passages_touching
from app.models.entity import Entity
from app.models.inject_queue import InjectStatus
from app.models.instance import Instance, InstanceStatus
from app.models.loop_state import InstanceLoopState, LoopStatus
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
from app.schemas.internal import DeliveryMode, InjectEnqueueRequest
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
from app.services.instance_factory import create_introduced_instance
from app.services.instance_restart import restart_instance_runtime

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


async def _refresh_instance_agent_config(
    db: DB, instance: Instance, *, actor_id: str | None = None
) -> dict | None:
    """Resolve BaseClass ⊕ Entity overlay into ``runtime_config.agent_config``.

    Also runs the v4.9.3 self-consistency check (has ⊇ required) and emits
    ``instance.knowledge_inconsistent`` when slugs are missing — the hint is
    non-blocking. Returns the warning dict (``{"missing": [...]}``) so the
    caller can attach it to the response, or ``None`` when consistent.
    """
    entity = await db.get(Entity, instance.entity_id)
    if entity is None or entity.deleted_at is not None:
        return None
    agent_config = await resolve_instance_agent_config(db, entity)
    runtime_config = dict(instance.runtime_config or {})
    runtime_config["agent_config"] = agent_config
    instance.runtime_config = runtime_config
    instance.active_hash = await compute_entity_migration_hash(db, entity)
    return await _check_and_warn(db, entity, instance, actor_id=actor_id)


async def _check_and_warn(
    db: DB,
    entity: Entity,
    instance: Instance,
    *,
    actor_id: str | None = None,
) -> dict | None:
    """v4.9.3 spawn hint: emit warning event + return it (never blocks)."""
    warning = await check_knowledge_consistency(db, entity)
    if warning is not None:
        await emit(
            INSTANCE_KNOWLEDGE_INCONSISTENT,
            actor_type="user",
            actor_id=actor_id,
            resource_type="instance",
            resource_id=instance.id,
            payload={**warning, "entity_id": entity.id},
            session=db,
        )
    return warning


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
    # v4.9.3 non-blocking spawn hint (set when the entity's has-knowledge
    # does not cover its required-knowledge): {"missing": [slug, ...]}.
    knowledge_consistency_warning: dict | None = None


class InjectEnqueueBody(InjectEnqueueRequest):
    """Public body for ``POST /instances/{id}/inject`` (V47-5).

    ``delivery_mode`` may be omitted: the V47-1 default table derives it
    from the instance's loop / lifecycle state. An explicit value always
    wins over the derivation. Inherits the V47-10 tldr hard rules from
    :class:`app.schemas.internal.InjectEnqueueRequest`.
    """

    delivery_mode: DeliveryMode | None = None


_ACTIVE_INSTANCE_STATUSES = frozenset(
    {
        InstanceStatus.running.value,
        InstanceStatus.pending.value,
        InstanceStatus.creating.value,
        InstanceStatus.deploying.value,
    }
)


async def _derive_delivery_mode(db: DB, instance: Instance) -> DeliveryMode:
    """V47-1 default table: loop state wins when present, else instance status.

    Loop state (authoritative): ``running`` -> ``soft_inject``; every other
    loop state (idle / completed / paused / interrupted / failed) -> ``wake``.
    Without a loop row, active lifecycle statuses (running / pending /
    creating / deploying) map to ``soft_inject`` and the rest to ``wake``.
    """
    result = await db.execute(
        select(InstanceLoopState).where(
            InstanceLoopState.instance_id == instance.id,
            InstanceLoopState.deleted_at.is_(None),
        )
    )
    loop_state = result.scalars().first()
    if loop_state is not None:
        if loop_state.loop_status == LoopStatus.running.value:
            return "soft_inject"
        return "wake"
    if instance.status in _ACTIVE_INSTANCE_STATUSES:
        return "soft_inject"
    return "wake"


def _is_k8s_available() -> bool:
    """P11c: probe whether a K8s cluster is reachable from this process.

    In local mode (no cluster, no ``KUBECONFIG``, no service-account
    token, or ``EYOT_K8S_DISABLED=true``), returns ``False`` so the
    deploy endpoint can short-circuit with 503 instead of crashing.
    """

    if os.environ.get("EYOT_K8S_DISABLED", "").lower() == "true":
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
) -> InstanceOutWithToken:
    """Create a new instance.

    Validates that the referenced entity and workspace exist (404 if not).
    The caller must hold at least the ``editor`` role in the target workspace.
    If ``workspace_path`` is omitted, one is generated automatically.
    A ``proxy_token`` is created automatically for P8 harness authentication.
    The initial status is ``creating``. The spawn pipeline (config
    resolution / knowledge payload / consistency hint / Instance row /
    topology placement) lives in the shared factory
    :func:`app.services.instance_factory.create_introduced_instance`.
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

    instance, _membership, consistency_warning = await create_introduced_instance(
        db,
        entity_id=body.entity_id,
        workspace_id=body.workspace_id,
        workspace_path=body.workspace_path,
        runtime_config_override=body.runtime_config,
        conflict_error=(
            "instance.already_exists",
            "errors.instance.already_exists",
            "Instance path taken or entity already introduced in this workspace",
        ),
        actor_id=current_user.user_id,
    )
    out = InstanceOutWithToken.model_validate(instance)
    out.knowledge_consistency_warning = consistency_warning
    return out


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
    ``EYOT_K8S_DISABLED=true``), falls back to P7's in-process DB
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
        # Emits instance.knowledge_inconsistent when has ⊉ required (event-only
        # on this legacy path — the response is the P7 InstanceOut contract).
        await _refresh_instance_agent_config(
            db, instance, actor_id=current_user.user_id
        )
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

    consistency_warning = await _refresh_instance_agent_config(
        db, instance, actor_id=current_user.user_id
    )

    record_id, ctx = await svc_deploy_existing_instance(
        instance_id,
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
        knowledge_consistency_warning=consistency_warning,
    )


@router.post("/{instance_id}/inject", status_code=status.HTTP_202_ACCEPTED)
async def inject_instance(
    instance_id: str,
    body: InjectEnqueueBody,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> dict:
    """Enqueue a v4.7 inject delivery for one instance (V47-5).

    Stripe-style action: the payload is persisted to the instance inject
    queue and the Host picks it up on its next control poll. The effective
    ``delivery_mode`` follows the V47-1 default table unless the caller
    provided one explicitly (explicit wins). Emits
    ``harness.inject_requested`` via the service and returns 202 with the
    queue row id.
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

    delivery_mode = body.delivery_mode or await _derive_delivery_mode(db, instance)
    payload: dict = {
        "content_refs": [ref.model_dump(exclude_none=True) for ref in body.content_refs],
        "gene_ids": body.gene_ids,
        "capability_ids": body.capability_ids,
    }
    if body.report is not None:
        payload["report"] = body.report
    if body.tldr:
        payload["tldr"] = body.tldr

    row = await enqueue_inject(
        db,
        instance_id=instance.id,
        kind=body.kind,
        delivery_mode=delivery_mode,
        payload=payload,
        tldr=body.tldr,
    )
    await db.commit()
    return {
        "queue_id": row.id,
        "instance_id": instance.id,
        "delivery_mode": delivery_mode,
        "status": InjectStatus.pending.value,
    }


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

    Pipeline semantics live in
    :func:`app.services.instance_restart.restart_instance_runtime` so the
    cerebellum restart endpoint shares the exact same code path.
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

    outcome = await restart_instance_runtime(
        db,
        instance=instance,
        entity=entity,
        triggered_by=current_user.user_id,
        reason=body.reason,
        force=body.force,
    )
    return RestartResultOut(
        restarted_at=outcome.restarted_at,
        instance_id=instance_id,
        old_hash=outcome.old_hash,
        new_hash=outcome.new_hash,
        status_after=outcome.status_after,
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
