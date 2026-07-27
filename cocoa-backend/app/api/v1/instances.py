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
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, CurrentUserDep
from app.core.errors import ConflictError, NotFoundError
from app.core.event_types import (
    INSTANCE_CREATED,
    INSTANCE_DELETED,
    INSTANCE_DEPLOYED,
    INSTANCE_FAILED,
    INSTANCE_RESTARTED,
    INSTANCE_STARTED,
    INSTANCE_STOPPED,
)
from app.core.events import emit
from app.core.openapi import add_error_responses
from app.core.pagination import OffsetPage, paginate_offset
from app.core.permissions import require_office_role
from app.core.workspace import generate_workspace_path
from app.models.employee import Employee
from app.models.instance import Instance, InstanceStatus
from app.models.office import Membership, Office
from app.schemas.instance import (
    InstanceCreate,
    InstanceOut,
    InstanceOutWithToken,
    InstanceUpdate,
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
    employee_id: str | None = None,
    office_id: str | None = None,
    status: str | None = None,
) -> OffsetPage:
    """Return a paginated list of active (non-deleted) instances.

    Optional filters: ``employee_id``, ``office_id``, ``status``.
    """
    stmt = select(Instance).where(Instance.deleted_at.is_(None))

    if employee_id is not None:
        stmt = stmt.where(Instance.employee_id == employee_id)
    if office_id is not None:
        await require_office_role(db, current_user.user_id, office_id, "viewer")
        stmt = stmt.where(Instance.office_id == office_id)
    else:
        stmt = stmt.where(
            Instance.office_id.in_(
                select(Membership.office_id).where(
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
    await require_office_role(db, current_user.user_id, instance.office_id, "editor")
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

    Validates that the referenced employee and office exist (404 if not).
    The caller must hold at least the ``editor`` role in the target office.
    If ``workspace_path`` is omitted, one is generated automatically.
    A ``proxy_token`` is created automatically for P8 harness authentication.
    The initial status is ``creating``.
    """
    employee = await db.get(Employee, body.employee_id)
    if employee is None or employee.deleted_at is not None:
        raise NotFoundError(
            "employee.not_found",
            "errors.employee.not_found",
            f"Employee '{body.employee_id}' not found",
        )

    office = await db.get(Office, body.office_id)
    if office is None or office.deleted_at is not None:
        raise NotFoundError(
            "office.not_found",
            "errors.office.not_found",
            f"Office '{body.office_id}' not found",
        )

    await require_office_role(db, current_user.user_id, body.office_id, "editor")

    workspace_path = body.workspace_path or generate_workspace_path(
        employee.slug, str(uuid4())
    )

    instance = Instance(
        employee_id=body.employee_id,
        office_id=body.office_id,
        workspace_path=workspace_path,
        status=InstanceStatus.creating.value,
        runtime_config=body.runtime_config,
        proxy_token=str(uuid4()),
    )
    db.add(instance)
    await emit(
        INSTANCE_CREATED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="instance",
        resource_id=instance.id,
        payload={"workspace_path": workspace_path, "office_id": body.office_id},
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

    await require_office_role(db, current_user.user_id, instance.office_id, "editor")

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

    await require_office_role(db, current_user.user_id, instance.office_id, "editor")

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

    await require_office_role(db, current_user.user_id, instance.office_id, "editor")

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


@router.post("/{instance_id}/deploy", response_model=DeployRecordOut)
async def deploy_instance(
    instance_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> DeployRecordOut:
    """Kick off the K8s deploy pipeline for this instance (P11c).

    Replaces the P7 in-process DB transition with a 9-step K8s
    pipeline driven by :func:`app.services.deploy_service.deploy_instance`.
    The DB-side :class:`DeployRecord` is created synchronously and
    returned to the caller; the actual K8s work runs as a fire-and-
    forget ``asyncio`` task whose progress is streamed via the SSE
    endpoint (``GET /api/v1/deploy/deploy-progress/{record_id}``).

    Returns 503 when no K8s cluster is reachable — local dev without a
    kubeconfig can keep working without crashing the deploy endpoint.
    """
    if not _is_k8s_available():
        raise HTTPException(
            status_code=503,
            detail="K8s not available; deploy pipeline requires K8s cluster (P11c local mode)",
        )

    instance = await db.get(Instance, instance_id)
    if instance is None or instance.deleted_at is not None:
        raise NotFoundError(
            "instance.not_found",
            "errors.instance.not_found",
            f"Instance '{instance_id}' not found",
        )

    await require_office_role(db, current_user.user_id, instance.office_id, "editor")

    record_id, ctx = await svc_deploy_instance(
        name=instance.workspace_path or str(instance.id),
        image_version="latest",
        office_id=instance.office_id,
        employee_id=instance.employee_id,
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


@router.post("/{instance_id}/start")
async def start_instance(
    instance_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> dict:
    """Transition instance to ``running`` and trigger a rebuild pipeline (P11c).

    Allowed from: ``pending``, ``deploying``. After the state transition
    commits, a fresh K8s deploy pipeline is kicked off via
    :func:`app.services.deploy_service.deploy_instance` — semantically a
    rebuild. The new :class:`DeployRecord` id is returned so the caller
    can subscribe to ``/api/v1/deploy/deploy-progress/{record_id}`` for
    live progress.
    """
    await _transition(
        instance_id,
        allowed=[InstanceStatus.pending.value, InstanceStatus.deploying.value],
        new_status=InstanceStatus.running.value,
        event_type=INSTANCE_STARTED,
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

    record_id, ctx = await svc_deploy_instance(
        name=instance.workspace_path or str(instance.id),
        image_version="latest",
        office_id=instance.office_id,
        employee_id=instance.employee_id,
        proxy_token=instance.proxy_token or "",
        triggered_by=current_user.user_id,
        db=db,
    )
    asyncio.create_task(svc_execute_deploy_pipeline(ctx))
    return {"record_id": record_id, "status": "running"}


@router.post("/{instance_id}/restart", response_model=InstanceOut)
async def restart_instance(
    instance_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> Instance:
    """Transition instance to ``restarting``.

    Allowed from: ``running``, ``failed``.
    """
    return await _transition(
        instance_id,
        allowed=[InstanceStatus.running.value, InstanceStatus.failed.value],
        new_status=InstanceStatus.restarting.value,
        event_type=INSTANCE_RESTARTED,
        db=db,
        current_user=current_user,
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
