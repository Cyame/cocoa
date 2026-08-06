"""Clone operations API routes (v4.4).

POST /api/v1/base-classes/{id}/clone
  - system source  -> can_manage_organization on target org (v4.9.4 C0)
  - other source   -> can_clone_base_class on source ancestry
POST /api/v1/entities/{id}/clone         -> can_clone_entity
POST /api/v1/organizations/{id}/clone    -> can_clone_organization
POST /api/v1/workspaces/{id}/clone      -> can_clone_workspace

Instance clone is permanently closed (no route registered -> 404).
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import DB, CurrentUserDep, XOrgIdHeader
from app.core.errors import ForbiddenError, NotFoundError
from app.core.openapi import add_error_responses
from app.core.org_scope import resolve_current_org_id
from app.core.permissions import require_permission, require_workspace_permission
from app.models.base_class import BaseClass
from app.models.entity import Entity
from app.models.organization import Organization
from app.schemas.base_class import BaseClassOut
from app.schemas.clone import CloneRequest
from app.schemas.entity import EntityOut
from app.schemas.organization import OrganizationOut
from app.schemas.workspace import WorkspaceOut
from app.services.clone import (
    clone_base_class,
    clone_entity,
    clone_organization,
    clone_workspace,
)

router = APIRouter(tags=["Clone"])
add_error_responses(router)


@router.post(
    "/base-classes/{preset_id}/clone",
    response_model=BaseClassOut,
    status_code=status.HTTP_201_CREATED,
)
async def clone_base_class_route(
    preset_id: str,
    body: CloneRequest,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> BaseClassOut:
    source = await db.get(BaseClass, preset_id)
    if source is None or source.deleted_at is not None:
        raise NotFoundError(
            "base_class.not_found",
            "errors.base_class.not_found",
            f"BaseClass '{preset_id}' not found",
        )
    if source.scope == "system":
        # v4.9.4 C0: a system-preset clone lands in a target org. Resolve the
        # X-Org header first, then the caller's default org (same as create).
        # A missing org context is a 403 ONLY for system sources.
        target_org_id = await resolve_current_org_id(
            db, current_user.user_id, x_organization_id
        )
        if target_org_id is None:
            raise ForbiddenError(
                "clone.no_org_context",
                "errors.clone.no_org_context",
                "No organization context for clone target",
                details={"resource": "base_class"},
            )
        # System source has no org/ns ancestry; gate on target-org management.
        await require_permission(
            db, current_user.user_id, "can_manage_organization",
            organization_id=target_org_id,
        )
    else:
        # Non-system sources keep the original path unchanged: no org context
        # is resolved, no 403 is raised, and the permission is checked on the
        # source ancestry. target_org_id is None and the service ignores it.
        target_org_id = None
        await require_permission(
            db, current_user.user_id, "can_clone_base_class",
            organization_id=source.organization_id,
            namespace_id=source.namespace_id,
        )
    new_bc = await clone_base_class(
        db, source_id=preset_id, actor_user_id=current_user.user_id,
        name=body.name, slug=body.slug, target_org_id=target_org_id,
    )
    await db.commit()
    await db.refresh(new_bc)
    from app.api.v1.base_classes import _base_class_out

    return await _base_class_out(db, new_bc)


@router.post(
    "/entities/{entity_id}/clone",
    response_model=EntityOut,
    status_code=status.HTTP_201_CREATED,
)
async def clone_entity_route(
    entity_id: str,
    body: CloneRequest,
    db: DB,
    current_user: CurrentUserDep,
) -> EntityOut:
    source = await db.get(Entity, entity_id)
    if source is None or source.deleted_at is not None:
        from app.core.errors import NotFoundError

        raise NotFoundError(
            "entity.not_found",
            "errors.entity.not_found",
            f"Entity '{entity_id}' not found",
        )
    await require_permission(
        db, current_user.user_id, "can_clone_entity",
        namespace_id=source.namespace_id,
    )
    new_entity = await clone_entity(
        db, source_id=entity_id, actor_user_id=current_user.user_id,
        name=body.name, slug=body.slug,
    )
    await db.commit()
    await db.refresh(new_entity)
    from app.api.v1.entities import _entity_out

    return await _entity_out(db, new_entity)


@router.post(
    "/organizations/{org_id}/clone",
    response_model=OrganizationOut,
    status_code=status.HTTP_201_CREATED,
)
async def clone_organization_route(
    org_id: str,
    body: CloneRequest,
    db: DB,
    current_user: CurrentUserDep,
) -> OrganizationOut:
    source = await db.get(Organization, org_id)
    if source is None or source.deleted_at is not None:
        from app.core.errors import NotFoundError

        raise NotFoundError(
            "organization.not_found",
            "errors.organization.not_found",
            f"Organization '{org_id}' not found",
        )
    await require_permission(
        db, current_user.user_id, "can_clone_organization",
        organization_id=org_id,
    )
    new_org = await clone_organization(
        db, source_id=org_id, actor_user_id=current_user.user_id,
        name=body.name, slug=body.slug,
    )
    await db.commit()
    await db.refresh(new_org)
    return OrganizationOut.model_validate(new_org)


@router.post(
    "/workspaces/{workspace_id}/clone",
    response_model=WorkspaceOut,
    status_code=status.HTTP_201_CREATED,
)
async def clone_workspace_route(
    workspace_id: str,
    body: CloneRequest,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> WorkspaceOut:
    await require_workspace_permission(
        db, current_user.user_id, workspace_id, "can_clone_workspace",
        x_organization_id=x_organization_id,
    )
    new_ws = await clone_workspace(
        db, source_id=workspace_id, actor_user_id=current_user.user_id,
        name=body.name, slug=body.slug,
    )
    await db.commit()
    await db.refresh(new_ws)
    return WorkspaceOut.model_validate(new_ws)
