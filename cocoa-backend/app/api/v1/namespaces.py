"""Namespace CRUD API (PRD-v2 scenario partition).

Routes:
    GET    /api/v1/namespaces           — list (with workspace/entity counts)
    GET    /api/v1/namespaces/{id}      — get one
    POST   /api/v1/namespaces           — create
    PATCH  /api/v1/namespaces/{id}      — update
    DELETE /api/v1/namespaces/{id}      — soft-delete
"""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import func, select, update

from app.api.deps import DB, CurrentUserDep, XOrgIdHeader
from app.core.errors import ConflictError, NotFoundError
from app.core.openapi import add_error_responses
from app.core.pagination import OffsetPage, paginate_offset
from app.core.permissions import require_permission
from app.core.tenant import get_default_namespace
from app.models.composer_message import ComposerMessage
from app.models.entity import Entity
from app.models.organization import Namespace, Organization
from app.models.workspace import Workspace
from app.schemas.namespace import (
    NamespaceCreate,
    NamespaceOut,
    NamespaceOutWithStats,
    NamespaceUpdate,
)

router = APIRouter(prefix="/namespaces", tags=["Namespaces"])
add_error_responses(router)


async def _resolve_org_id(db: DB, org_id: str | None) -> str:
    if org_id:
        org = await db.get(Organization, org_id)
        if org is None or org.deleted_at is not None:
            raise NotFoundError(
                "organization.not_found",
                "errors.organization.not_found",
                f"Organization '{org_id}' not found",
            )
        return org.id
    result = await db.execute(
        select(Organization).where(
            Organization.slug == "default",
            Organization.deleted_at.is_(None),
        )
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise NotFoundError(
            "organization.not_found",
            "errors.organization.not_found",
            "Default organization not found",
        )
    return org.id


async def _namespace_stats(
    db: DB, namespace_ids: list[str]
) -> dict[str, tuple[int, int]]:
    if not namespace_ids:
        return {}
    ws_q = (
        select(Workspace.namespace_id, func.count())
        .where(
            Workspace.namespace_id.in_(namespace_ids),
            Workspace.deleted_at.is_(None),
        )
        .group_by(Workspace.namespace_id)
    )
    ent_q = (
        select(Entity.namespace_id, func.count())
        .where(
            Entity.namespace_id.in_(namespace_ids),
            Entity.deleted_at.is_(None),
        )
        .group_by(Entity.namespace_id)
    )
    ws_counts = {row[0]: row[1] for row in await db.execute(ws_q)}
    ent_counts = {row[0]: row[1] for row in await db.execute(ent_q)}
    return {
        ns_id: (ws_counts.get(ns_id, 0), ent_counts.get(ns_id, 0))
        for ns_id in namespace_ids
    }


def _to_out_with_stats(
    ns: Namespace, ws_count: int, ent_count: int
) -> NamespaceOutWithStats:
    return NamespaceOutWithStats(
        id=ns.id,
        org_id=ns.org_id,
        slug=ns.slug,
        name=ns.name,
        description=ns.description,
        tags=ns.tags,
        created_at=ns.created_at,
        updated_at=ns.updated_at,
        workspace_count=ws_count,
        entity_count=ent_count,
    )


@router.get("", response_model=OffsetPage[NamespaceOutWithStats])
async def list_namespaces(
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
    limit: int = 50,
    offset: int = 0,
    org_id: str | None = None,
) -> OffsetPage:
    """Return paginated namespaces with workspace and entity counts.

    Filtered by the active organization context (``X-Organization-Id`` header
    or the user's single OrganizationContract), falling back to the legacy
    ``org_id`` query param for backward compatibility.
    """
    from app.core.org_scope import resolve_current_org_id

    ctx_org_id = await resolve_current_org_id(
        db, current_user.user_id, x_organization_id
    )
    stmt = select(Namespace).where(Namespace.deleted_at.is_(None))
    # Prefer the resolved org context; legacy query param overrides when set.
    effective_org = org_id or ctx_org_id
    if effective_org is not None:
        stmt = stmt.where(Namespace.org_id == effective_org)
    stmt = stmt.order_by(Namespace.created_at)
    page = await paginate_offset(db, stmt, offset, min(limit, 200))
    ids = [item.id for item in page.items]
    stats = await _namespace_stats(db, ids)
    page.items = [
        _to_out_with_stats(item, *stats.get(item.id, (0, 0)))
        for item in page.items
    ]
    return page


@router.get("/{namespace_id}", response_model=NamespaceOutWithStats)
async def get_namespace(
    namespace_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> NamespaceOutWithStats:
    """Return a single namespace with counts."""
    ns = await db.get(Namespace, namespace_id)
    if ns is None or ns.deleted_at is not None:
        raise NotFoundError(
            "namespace.not_found",
            "errors.namespace.not_found",
            f"Namespace '{namespace_id}' not found",
        )
    ws_count, ent_count = (await _namespace_stats(db, [ns.id]))[ns.id]
    return _to_out_with_stats(ns, ws_count, ent_count)


@router.post("", response_model=NamespaceOut, status_code=status.HTTP_201_CREATED)
async def create_namespace(
    body: NamespaceCreate,
    db: DB,
    current_user: CurrentUserDep,
) -> Namespace:
    """Create a namespace under the default (or specified) Organization."""
    org_id = await _resolve_org_id(db, body.org_id)
    await require_permission(
        db, current_user.user_id, "can_manage_namespace", organization_id=org_id
    )
    existing = await db.execute(
        select(Namespace).where(
            Namespace.org_id == org_id,
            Namespace.slug == body.slug,
            Namespace.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(
            "namespace.slug_taken",
            "errors.namespace.slug_taken",
            f"Namespace slug '{body.slug}' is already taken",
        )
    ns = Namespace(
        org_id=org_id,
        slug=body.slug,
        name=body.name,
        description=body.description,
        tags=body.tags,
    )
    db.add(ns)
    await db.commit()
    await db.refresh(ns)
    return ns


@router.patch("/{namespace_id}", response_model=NamespaceOut)
async def update_namespace(
    namespace_id: str,
    body: NamespaceUpdate,
    db: DB,
    current_user: CurrentUserDep,
) -> Namespace:
    """Partial-update a namespace. Slug is immutable."""
    ns = await db.get(Namespace, namespace_id)
    if ns is None or ns.deleted_at is not None:
        raise NotFoundError(
            "namespace.not_found",
            "errors.namespace.not_found",
            f"Namespace '{namespace_id}' not found",
        )
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(ns, field, value)
    await db.commit()
    await db.refresh(ns)
    return ns


@router.delete("/{namespace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_namespace(
    namespace_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> None:
    """Soft-delete a namespace. The seeded ``default`` namespace is protected."""
    default_ns = await get_default_namespace(db)
    if namespace_id == default_ns.id:
        raise ConflictError(
            "namespace.cannot_delete_default",
            "errors.namespace.cannot_delete_default",
            "The default namespace cannot be deleted",
        )
    ns = await db.get(Namespace, namespace_id)
    if ns is None or ns.deleted_at is not None:
        raise NotFoundError(
            "namespace.not_found",
            "errors.namespace.not_found",
            f"Namespace '{namespace_id}' not found",
        )
    ns.soft_delete()
    await db.execute(
        update(ComposerMessage)
        .where(
            ComposerMessage.namespace_id == namespace_id,
            ComposerMessage.deleted_at.is_(None),
        )
        .values(deleted_at=func.now())
    )
    await db.commit()
