"""Instance API routes — CRUD + lifecycle state machine action endpoints.

P7 implements the full Instance lifecycle: create → deploy → start →
restart → stop → fail → delete. Each state transition is governed by
an explicit allowed-status whitelist; invalid transitions return 409.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, status
from pydantic import BaseModel
from sqlalchemy import func, select, update

from app.api.deps import DB, CurrentUserDep
from app.core.errors import ConflictError, NotFoundError
from app.core.event_types import (
    INSTANCE_CREATED,
    INSTANCE_DELETED,
    INSTANCE_DEPLOYING,
    INSTANCE_FAILED,
    INSTANCE_RESTARTING,
    INSTANCE_RUNNING,
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

router = APIRouter(prefix="/instances", tags=["Instances"])
add_error_responses(router)


class FailBody(BaseModel):
    """Payload for ``POST /instances/{instance_id}/fail``."""

    reason: str


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
    await db.commit()
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

    await db.commit()
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


@router.post("/{instance_id}/deploy", response_model=InstanceOut)
async def deploy_instance(
    instance_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> Instance:
    """Transition instance to ``deploying``.

    Allowed from: ``creating``, ``restarting``.
    """
    return await _transition(
        instance_id,
        allowed=[InstanceStatus.creating.value, InstanceStatus.restarting.value],
        new_status=InstanceStatus.deploying.value,
        event_type=INSTANCE_DEPLOYING,
        db=db,
        current_user=current_user,
    )


@router.post("/{instance_id}/start", response_model=InstanceOut)
async def start_instance(
    instance_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> Instance:
    """Transition instance to ``running``.

    Allowed from: ``pending``, ``deploying``.
    """
    return await _transition(
        instance_id,
        allowed=[InstanceStatus.pending.value, InstanceStatus.deploying.value],
        new_status=InstanceStatus.running.value,
        event_type=INSTANCE_RUNNING,
        db=db,
        current_user=current_user,
    )


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
        event_type=INSTANCE_RESTARTING,
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

    Allowed from: ``running``. No lifecycle event is emitted for stop.
    """
    return await _transition(
        instance_id,
        allowed=[InstanceStatus.running.value],
        new_status=InstanceStatus.pending.value,
        event_type=None,
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
