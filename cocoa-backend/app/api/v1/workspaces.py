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
from sqlalchemy import select

from app.api.deps import DB, CurrentUserDep
from app.core.errors import ConflictError, NotFoundError
from app.core.openapi import add_error_responses
from app.core.pagination import OffsetPage, paginate_offset
from app.core.tenant import resolve_namespace_id
from app.models.workspace import Membership, MembershipRole, Workspace
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
    """Soft-delete an workspace.

    The record is marked as deleted (``deleted_at`` is set) but not physically
    removed from the database.  Raises 404 if the workspace does not exist.
    """
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None or workspace.deleted_at is not None:
        raise NotFoundError(
            "workspace.not_found",
            "errors.workspace.not_found",
            f"Workspace '{workspace_id}' not found",
        )

    workspace.soft_delete()
    await db.commit()
