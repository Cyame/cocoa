"""Workspace CRUD API routes.

Endpoints for managing collaboration workspaces.  All mutations create,
update, and soft-delete workspaces.  The ``slug`` field has a partial unique
index and is checked for conflicts on both create and update.

Routes (all require authentication):
    GET    /api/v1/workspaces       — List all active workspaces (offset page)
    GET    /api/v1/workspaces/{id}  — Get a single workspace
    POST   /api/v1/workspaces       — Create a new workspace (auto-adds creator as owner)
    PATCH  /api/v1/workspaces/{id}  — Update an existing workspace
    DELETE /api/v1/workspaces/{id}  — Soft-delete an workspace
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select, update

from app.api.deps import DB, CurrentUserDep
from app.core.errors import ConflictError, NotFoundError
from app.core.namespace_contract import ensure_namespace_contract
from app.core.openapi import add_error_responses
from app.core.pagination import OffsetPage, paginate_offset
from app.core.tenant import resolve_namespace_id
from app.models.workspace import Membership, MembershipRole, Workspace
from app.schemas.instance import InstanceOutWithToken
from app.schemas.introduce import IntroduceEntityRequest
from app.schemas.workspace import WorkspaceCreate, WorkspaceOut, WorkspaceUpdate

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])
add_error_responses(router)


@router.get("", response_model=OffsetPage[WorkspaceOut])
async def list_workspaces(
    db: DB,
    current_user: CurrentUserDep,
    limit: int = 50,
    offset: int = 0,
    namespace_id: str | None = Query(None),
) -> OffsetPage:
    """Return a paginated list of active (non-deleted) workspaces."""
    stmt = (
        select(Workspace)
        .where(Workspace.deleted_at.is_(None))
        .order_by(Workspace.created_at)
    )
    if namespace_id is not None:
        stmt = stmt.where(Workspace.namespace_id == namespace_id)
    return await paginate_offset(db, stmt, offset, min(limit, 200))


@router.get("/{workspace_id}", response_model=WorkspaceOut)
async def get_workspace(
    workspace_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> Workspace:
    """Return a single workspace by ID.

    Raises 404 if the workspace does not exist or has been soft-deleted.
    """
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None or workspace.deleted_at is not None:
        raise NotFoundError(
            "workspace.not_found",
            "errors.workspace.not_found",
            f"Workspace '{workspace_id}' not found",
        )
    return workspace


@router.post("", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    body: WorkspaceCreate,
    db: DB,
    current_user: CurrentUserDep,
) -> Workspace:
    """Create a new workspace.

    The authenticated creator is automatically added as a :class:`Membership`
    with ``role='owner'`` so that the workspace is immediately usable by the
    creator (P14b-onboard2 onboarding fix).  Without this, the creator
    would hit "not a member of workspace" when fetching the workspace detail
    view.

    Raises 409 if an workspace with the same slug already exists (active).
    """
    namespace_id = await resolve_namespace_id(db, body.namespace_id)
    existing = await db.execute(
        select(Workspace).where(
            Workspace.namespace_id == namespace_id,
            Workspace.slug == body.slug,
            Workspace.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(
            "workspace.slug_taken",
            "errors.workspace.slug_taken",
            f"Workspace slug '{body.slug}' is already taken",
        )

    workspace = Workspace(
        name=body.name,
        slug=body.slug,
        namespace_id=namespace_id,
    )
    db.add(workspace)
    await db.flush()

    from app.models.central_hub import CentralHub, CerebellumAgent, Vault

    hub = CentralHub(workspace_id=workspace.id)
    db.add(hub)
    await db.flush()
    db.add(
        CerebellumAgent(
            central_hub_id=hub.id,
            name="cerebellum",
            base_slug="cerebellum-baseclass",
            loop_status="idle",
        )
    )
    db.add(Vault(workspace_id=workspace.id))

    await ensure_namespace_contract(
        db,
        namespace_id=namespace_id,
        user_id=current_user.user_id,
        role="owner",
    )

    # P14b-onboard2: auto-create the creator as owner so the workspace is
    # immediately navigable. (0, 0) is fine because the owner is the first
    # membership in a fresh workspace.
    owner_membership = Membership(
        workspace_id=workspace.id,
        user_id=current_user.user_id,
        posx=0,
        posy=0,
        role=MembershipRole.owner.value,
    )
    db.add(owner_membership)

    await db.commit()
    await db.refresh(workspace)
    return workspace


@router.patch("/{workspace_id}", response_model=WorkspaceOut)
async def update_workspace(
    workspace_id: str,
    body: WorkspaceUpdate,
    db: DB,
    current_user: CurrentUserDep,
) -> Workspace:
    """Update an existing workspace.

    Only the fields provided in the request body are updated (partial update).
    The ``slug`` can be changed but is checked for uniqueness against other
    active workspaces.  Raises 404 if the workspace does not exist.
    """
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None or workspace.deleted_at is not None:
        raise NotFoundError(
            "workspace.not_found",
            "errors.workspace.not_found",
            f"Workspace '{workspace_id}' not found",
        )

    patch_data = body.model_dump(exclude_unset=True)

    # Check slug uniqueness if slug is being changed (and differs from current)
    if "slug" in patch_data and patch_data["slug"] != workspace.slug:
        existing = await db.execute(
            select(Workspace).where(
                Workspace.slug == patch_data["slug"],
                Workspace.deleted_at.is_(None),
                Workspace.id != workspace_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ConflictError(
                "workspace.slug_taken",
                "errors.workspace.slug_taken",
                f"Workspace slug '{patch_data['slug']}' is already taken",
            )

    for field, value in patch_data.items():
        setattr(workspace, field, value)

    await db.commit()
    await db.refresh(workspace)
    return workspace


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> None:
    """Soft-delete a workspace and cascade to instances / memberships / hub.

    PRD-v3.4: 迷失者 lifecycle ≤ workspace. Does not touch Entity or 契印.
    """
    from app.models.central_hub import (
        CentralHub,
        CerebellumAgent,
        Vault,
        VaultEntry,
    )
    from app.models.instance import Instance
    from app.models.workspace import Passage

    workspace = await db.get(Workspace, workspace_id)
    if workspace is None or workspace.deleted_at is not None:
        raise NotFoundError(
            "workspace.not_found",
            "errors.workspace.not_found",
            f"Workspace '{workspace_id}' not found",
        )

    # Soft-delete instances (K8s teardown best-effort left to instance delete path).
    inst_rows = (
        await db.execute(
            select(Instance).where(
                Instance.workspace_id == workspace_id,
                Instance.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    for inst in inst_rows:
        inst.soft_delete()

    await db.execute(
        update(Membership)
        .where(
            Membership.workspace_id == workspace_id,
            Membership.deleted_at.is_(None),
        )
        .values(deleted_at=func.now())
    )
    await db.execute(
        update(Passage)
        .where(
            Passage.workspace_id == workspace_id,
            Passage.deleted_at.is_(None),
        )
        .values(deleted_at=func.now())
    )

    hubs = (
        await db.execute(
            select(CentralHub).where(
                CentralHub.workspace_id == workspace_id,
                CentralHub.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    for hub in hubs:
        agents = (
            await db.execute(
                select(CerebellumAgent).where(
                    CerebellumAgent.central_hub_id == hub.id,
                    CerebellumAgent.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        for agent in agents:
            agent.soft_delete()
        hub.soft_delete()

    vaults = (
        await db.execute(
            select(Vault).where(
                Vault.workspace_id == workspace_id,
                Vault.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    for vault in vaults:
        entries = (
            await db.execute(
                select(VaultEntry).where(
                    VaultEntry.vault_id == vault.id,
                    VaultEntry.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        for entry in entries:
            entry.soft_delete()
        vault.soft_delete()

    from app.models.composer_message import ComposerMessage

    await db.execute(
        update(ComposerMessage)
        .where(
            ComposerMessage.workspace_id == workspace_id,
            ComposerMessage.deleted_at.is_(None),
        )
        .values(deleted_at=func.now())
    )

    workspace.soft_delete()
    await db.commit()


@router.post(
    "/{workspace_id}/introduce-entity",
    response_model=InstanceOutWithToken,
    status_code=status.HTTP_201_CREATED,
)
async def introduce_entity(
    workspace_id: str,
    body: IntroduceEntityRequest,
    db: DB,
    current_user: CurrentUserDep,
) -> InstanceOutWithToken:
    """Introduce a 眷族 into this workspace → create 迷失者 (Instance).

    At most one active instance per (workspace, entity). Portal primary path.
    """
    from uuid import uuid4

    from app.core.event_types import INSTANCE_CREATED
    from app.core.events import emit
    from app.core.migration_hash import compute_entity_migration_hash
    from app.core.overlay import resolve_instance_agent_config
    from app.core.permissions import require_workspace_role
    from app.core.workspace import generate_workspace_path
    from app.models.entity import Entity
    from app.models.instance import Instance, InstanceStatus

    await require_workspace_role(db, current_user.user_id, workspace_id, "editor")

    workspace = await db.get(Workspace, workspace_id)
    if workspace is None or workspace.deleted_at is not None:
        raise NotFoundError(
            "workspace.not_found",
            "errors.workspace.not_found",
            f"Workspace '{workspace_id}' not found",
        )

    entity = await db.get(Entity, body.entity_id)
    if entity is None or entity.deleted_at is not None:
        raise NotFoundError(
            "entity.not_found",
            "errors.entity.not_found",
            f"Entity '{body.entity_id}' not found",
        )
    if entity.namespace_id != workspace.namespace_id:
        raise ConflictError(
            "entity.namespace_mismatch",
            "errors.entity.namespace_mismatch",
            "Entity does not belong to this workspace's namespace",
        )

    existing = await db.execute(
        select(Instance).where(
            Instance.workspace_id == workspace_id,
            Instance.entity_id == body.entity_id,
            Instance.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(
            "instance.entity_already_introduced",
            "errors.instance.entity_already_introduced",
            "This entity already has a lost one in this workspace",
        )

    # Ensure entity.migration_hash is populated so live-status outdated stays false.
    if not entity.migration_hash:
        entity.migration_hash = compute_entity_migration_hash(entity)

    workspace_path = generate_workspace_path(entity.slug, str(uuid4()))
    agent_config = await resolve_instance_agent_config(db, entity)
    runtime_config = {"agent_config": agent_config}
    instance = Instance(
        entity_id=body.entity_id,
        workspace_id=workspace_id,
        workspace_path=workspace_path,
        status=InstanceStatus.creating.value,
        runtime_config=runtime_config,
        proxy_token=str(uuid4()),
        active_hash=entity.migration_hash or compute_entity_migration_hash(entity),
    )
    db.add(instance)
    await db.flush()

    occupied = {
        (row.posx, row.posy)
        for row in (
            await db.execute(
                select(Membership.posx, Membership.posy).where(
                    Membership.workspace_id == workspace_id,
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
    instance_membership = Membership(
        workspace_id=workspace_id,
        instance_id=instance.id,
        user_id=None,
        posx=posx,
        posy=posy,
        role=MembershipRole.viewer.value,
    )
    db.add(instance_membership)
    await emit(
        INSTANCE_CREATED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="instance",
        resource_id=instance.id,
        payload={"workspace_path": workspace_path, "workspace_id": workspace_id},
        session=db,
    )
    await db.commit()
    await db.refresh(instance)

    # PRD-v3.4.1: auto-deploy the introduced instance (best-effort).
    deploy_record_id: str | None = None
    try:
        import asyncio
        import logging

        from app.api.v1.instances import _is_k8s_available, _transition
        from app.core.event_types import INSTANCE_DEPLOYED
        from app.services.deploy_service import (
            deploy_existing_instance,
            execute_deploy_pipeline,
        )

        if _is_k8s_available():
            _record_id, ctx = await deploy_existing_instance(
                instance.id,
                image_version="latest",
                triggered_by=current_user.user_id,
                db=db,
            )
            deploy_record_id = _record_id
            asyncio.create_task(execute_deploy_pipeline(ctx))
        else:
            await _transition(
                instance.id,
                allowed=[InstanceStatus.creating.value],
                new_status=InstanceStatus.deploying.value,
                event_type=INSTANCE_DEPLOYED,
                db=db,
                current_user=current_user,
            )
            await db.refresh(instance)
    except Exception:  # noqa: BLE001 — introduce must still succeed
        logging.getLogger(__name__).exception(
            "auto-deploy after introduce failed instance_id=%s", instance.id
        )

    out = InstanceOutWithToken.model_validate(instance)
    return out.model_copy(update={"deploy_record_id": deploy_record_id})
