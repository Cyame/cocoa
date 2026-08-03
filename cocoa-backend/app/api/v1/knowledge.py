"""v4.2 Knowledge System — knowledge_entries / knowledge_dimensions CRUD.

Routes:
    GET    /api/v1/knowledge                  — list (login + org-visible)
    GET    /api/v1/knowledge/{entry_id}       — get by id
    POST   /api/v1/knowledge                  — create (can_manage_knowledge)
    PATCH  /api/v1/knowledge/{entry_id}       — update (can_manage_knowledge)
    DELETE /api/v1/knowledge/{entry_id}       — soft-delete (can_manage_knowledge)
    GET    /api/v1/knowledge-dimensions       — list
    GET    /api/v1/knowledge-dimensions/{id}  — get by id
    POST   /api/v1/knowledge-dimensions       — create
    PATCH  /api/v1/knowledge-dimensions/{id}  — update
    DELETE /api/v1/knowledge-dimensions/{id}  — soft-delete

Write-time H2 validation delegates to ``validate_scope_fks`` (org_scope.py):
system → all ownership ids NULL; org → organization_id only; namespace →
organization_id + namespace_id; workspace → all three. ``key`` / ``slug`` are
normalized to lowercase at write time so case variants cannot inject duplicate
rows under the partial unique index ``uq_knowledge_entries_active_key`` /
``uq_knowledge_dimensions_active_slug`` (COALESCE sentinel).
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, CurrentUserDep, XOrgIdHeader
from app.core.errors import ConflictError, NotFoundError
from app.core.openapi import add_error_responses
from app.core.org_scope import (
    resolve_current_org_id,
    scoped_visibility_clause,
    validate_scope_fks,
)
from app.core.pagination import OffsetPage, paginate_offset
from app.core.permissions import require_permission
from app.models.knowledge import (
    SCOPE_NULL_SENTINEL,
    KnowledgeDimension,
    KnowledgeEntry,
)
from app.schemas.knowledge import (
    KnowledgeDimensionCreate,
    KnowledgeDimensionOut,
    KnowledgeDimensionUpdate,
    KnowledgeEntryCreate,
    KnowledgeEntryOut,
    KnowledgeEntryUpdate,
)

_MANAGE_ATOM = "can_manage_knowledge"
_ENTRY_RESOURCE = "knowledge_entry"
_DIMENSION_RESOURCE = "knowledge_dimension"


def _lower_key(value: str) -> str:
    return value.strip().lower()


def _lower_slug(value: str) -> str:
    return value.strip().lower()


def _coalesce_match(column, value: str | None):
    """Equality against the COALESCE NULL sentinel used by the unique indexes."""
    return func.coalesce(column, SCOPE_NULL_SENTINEL) == (value or SCOPE_NULL_SENTINEL)


router = APIRouter(prefix="/knowledge", tags=["Knowledge"])
add_error_responses(router)

dimensions_router = APIRouter(prefix="/knowledge-dimensions", tags=["KnowledgeDimensions"])
add_error_responses(dimensions_router)


async def _get_active_entry(db: DB, entry_id: str) -> KnowledgeEntry:
    entry = await db.get(KnowledgeEntry, entry_id)
    if entry is None or entry.deleted_at is not None:
        raise NotFoundError(
            "knowledge.not_found",
            "errors.knowledge.not_found",
            f"Knowledge entry '{entry_id}' not found",
        )
    return entry


async def _get_active_dimension(db: DB, dimension_id: str) -> KnowledgeDimension:
    dimension = await db.get(KnowledgeDimension, dimension_id)
    if dimension is None or dimension.deleted_at is not None:
        raise NotFoundError(
            "knowledge_dimension.not_found",
            "errors.knowledge_dimension.not_found",
            f"Knowledge dimension '{dimension_id}' not found",
        )
    return dimension


async def _entry_key_taken(
    db: DB, scope: str, org_id: str | None, ns_id: str | None, ws_id: str | None, key: str
) -> bool:
    result = await db.execute(
        select(KnowledgeEntry.id)
        .where(
            KnowledgeEntry.deleted_at.is_(None),
            KnowledgeEntry.scope == scope,
            _coalesce_match(KnowledgeEntry.organization_id, org_id),
            _coalesce_match(KnowledgeEntry.namespace_id, ns_id),
            _coalesce_match(KnowledgeEntry.workspace_id, ws_id),
            KnowledgeEntry.key == key,
        )
    )
    return result.scalar_one_or_none() is not None


async def _dimension_slug_taken(
    db: DB, scope: str, org_id: str | None, ns_id: str | None, ws_id: str | None, slug: str
) -> bool:
    result = await db.execute(
        select(KnowledgeDimension.id)
        .where(
            KnowledgeDimension.deleted_at.is_(None),
            KnowledgeDimension.scope == scope,
            _coalesce_match(KnowledgeDimension.organization_id, org_id),
            _coalesce_match(KnowledgeDimension.namespace_id, ns_id),
            _coalesce_match(KnowledgeDimension.workspace_id, ws_id),
            KnowledgeDimension.slug == slug,
        )
    )
    return result.scalar_one_or_none() is not None


async def _fence_cross_org(
    current_org_id: str | None,
    resource_scope: str,
    row_org_id: str | None,
    row_id: str,
    *,
    error_code: str,
) -> None:
    """Hide cross-org rows on patch/delete (matches ai_genes)."""
    if current_org_id is not None and resource_scope != "system":
        if row_org_id != current_org_id:
            raise NotFoundError(
                error_code,
                f"errors.{error_code}",
                f"Resource '{row_id}' not found",
            )


# ---------------------------------------------------------------------------
# /api/v1/knowledge
# ---------------------------------------------------------------------------


@router.get("", response_model=OffsetPage[KnowledgeEntryOut])
async def list_knowledge_entries(
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
    scope: str | None = Query(None),
    limit: int = 50,
    offset: int = 0,
) -> OffsetPage:
    """Return knowledge entries visible in the current org context."""
    current_org_id = await resolve_current_org_id(
        db, current_user.user_id, x_organization_id
    )
    stmt = (
        select(KnowledgeEntry)
        .where(KnowledgeEntry.deleted_at.is_(None))
        .where(
            scoped_visibility_clause(
                KnowledgeEntry, current_org_id, scope, include_workspace=True
            )
        )
        .order_by(KnowledgeEntry.key)
    )
    return await paginate_offset(db, stmt, offset, min(limit, 200))


@router.get("/{entry_id}", response_model=KnowledgeEntryOut)
async def get_knowledge_entry(
    entry_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> KnowledgeEntry:
    """Return a single knowledge entry visible in the current org context."""
    current_org_id = await resolve_current_org_id(
        db, current_user.user_id, x_organization_id
    )
    result = await db.execute(
        select(KnowledgeEntry).where(
            KnowledgeEntry.id == entry_id,
            KnowledgeEntry.deleted_at.is_(None),
            scoped_visibility_clause(
                KnowledgeEntry, current_org_id, None, include_workspace=True
            ),
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise NotFoundError(
            "knowledge.not_found",
            "errors.knowledge.not_found",
            f"Knowledge entry '{entry_id}' not found",
        )
    return entry


@router.post("", response_model=KnowledgeEntryOut, status_code=status.HTTP_201_CREATED)
async def create_knowledge_entry(
    body: KnowledgeEntryCreate,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> KnowledgeEntry:
    """Create a knowledge entry (requires can_manage_knowledge)."""
    from app.core.scope_guard import ensure_scope_create_allowed

    current_org_id = await resolve_current_org_id(
        db, current_user.user_id, x_organization_id
    )
    # Gate on the request org context first: a caller without the atom must be
    # rejected even when the payload itself would fail scope validation.
    await require_permission(
        db,
        current_user.user_id,
        _MANAGE_ATOM,
        organization_id=current_org_id,
    )
    # Strict write-time H2 validation: the client must supply the ownership ids
    # its scope demands (no current_org_id fallback for entries).
    org_id, ns_id, ws_id = validate_scope_fks(
        body.scope,
        body.organization_id,
        body.namespace_id,
        workspace_id=body.workspace_id,
        current_org_id=None,
    )
    ensure_scope_create_allowed(body.scope, resource=_ENTRY_RESOURCE)
    await require_permission(
        db,
        current_user.user_id,
        _MANAGE_ATOM,
        organization_id=org_id,
        namespace_id=ns_id,
        workspace_id=ws_id,
    )
    key = _lower_key(body.key)
    if await _entry_key_taken(db, body.scope, org_id, ns_id, ws_id, key):
        raise ConflictError(
            "knowledge.key_conflict",
            "errors.knowledge.key_conflict",
            f"Knowledge entry key '{key}' already exists in this scope",
        )
    entry = KnowledgeEntry(
        key=key,
        title=body.title,
        body=body.body,
        dimension_id=body.dimension_id,
        scope=body.scope,
        organization_id=org_id,
        namespace_id=ns_id,
        workspace_id=ws_id,
        entity_id=body.entity_id,
        instance_id=body.instance_id,
    )
    db.add(entry)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError(
            "knowledge.key_conflict",
            "errors.knowledge.key_conflict",
            f"Knowledge entry key '{key}' already exists in this scope",
        )
    await db.refresh(entry)
    return entry


@router.patch("/{entry_id}", response_model=KnowledgeEntryOut)
async def update_knowledge_entry(
    entry_id: str,
    body: KnowledgeEntryUpdate,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> KnowledgeEntry:
    """Partial-update a knowledge entry. System rows are read-only."""
    from app.core.scope_guard import ensure_scope_mutable

    current_org_id = await resolve_current_org_id(
        db, current_user.user_id, x_organization_id
    )
    entry = await _get_active_entry(db, entry_id)
    ensure_scope_mutable(entry.scope, resource=_ENTRY_RESOURCE, row_id=entry_id)
    await require_permission(
        db,
        current_user.user_id,
        _MANAGE_ATOM,
        organization_id=entry.organization_id,
        namespace_id=entry.namespace_id,
        workspace_id=entry.workspace_id,
    )
    await _fence_cross_org(
        current_org_id, entry.scope, entry.organization_id, entry_id,
        error_code="knowledge.not_found",
    )
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "key" and value is not None:
            value = _lower_key(value)
        setattr(entry, field, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError(
            "knowledge.key_conflict",
            "errors.knowledge.key_conflict",
            f"Knowledge entry key '{entry.key}' already exists in this scope",
        )
    await db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_entry(
    entry_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> None:
    """Soft-delete a knowledge entry. System rows are read-only."""
    from app.core.scope_guard import ensure_scope_mutable

    current_org_id = await resolve_current_org_id(
        db, current_user.user_id, x_organization_id
    )
    entry = await _get_active_entry(db, entry_id)
    ensure_scope_mutable(entry.scope, resource=_ENTRY_RESOURCE, row_id=entry_id)
    await require_permission(
        db,
        current_user.user_id,
        _MANAGE_ATOM,
        organization_id=entry.organization_id,
        namespace_id=entry.namespace_id,
        workspace_id=entry.workspace_id,
    )
    await _fence_cross_org(
        current_org_id, entry.scope, entry.organization_id, entry_id,
        error_code="knowledge.not_found",
    )
    entry.soft_delete()
    await db.commit()


# ---------------------------------------------------------------------------
# /api/v1/knowledge-dimensions
# ---------------------------------------------------------------------------


@dimensions_router.get("", response_model=OffsetPage[KnowledgeDimensionOut])
async def list_knowledge_dimensions(
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
    scope: str | None = Query(None),
    limit: int = 50,
    offset: int = 0,
) -> OffsetPage:
    """Return knowledge dimensions visible in the current org context."""
    current_org_id = await resolve_current_org_id(
        db, current_user.user_id, x_organization_id
    )
    stmt = (
        select(KnowledgeDimension)
        .where(KnowledgeDimension.deleted_at.is_(None))
        .where(
            scoped_visibility_clause(
                KnowledgeDimension, current_org_id, scope, include_workspace=True
            )
        )
        .order_by(KnowledgeDimension.name)
    )
    return await paginate_offset(db, stmt, offset, min(limit, 200))


@dimensions_router.get("/{dimension_id}", response_model=KnowledgeDimensionOut)
async def get_knowledge_dimension(
    dimension_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> KnowledgeDimension:
    """Return a single knowledge dimension visible in the current org context."""
    current_org_id = await resolve_current_org_id(
        db, current_user.user_id, x_organization_id
    )
    result = await db.execute(
        select(KnowledgeDimension).where(
            KnowledgeDimension.id == dimension_id,
            KnowledgeDimension.deleted_at.is_(None),
            scoped_visibility_clause(
                KnowledgeDimension, current_org_id, None, include_workspace=True
            ),
        )
    )
    dimension = result.scalar_one_or_none()
    if dimension is None:
        raise NotFoundError(
            "knowledge_dimension.not_found",
            "errors.knowledge_dimension.not_found",
            f"Knowledge dimension '{dimension_id}' not found",
        )
    return dimension


@dimensions_router.post(
    "", response_model=KnowledgeDimensionOut, status_code=status.HTTP_201_CREATED
)
async def create_knowledge_dimension(
    body: KnowledgeDimensionCreate,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> KnowledgeDimension:
    """Create a knowledge dimension (requires can_manage_knowledge)."""
    from app.core.scope_guard import ensure_scope_create_allowed

    ensure_scope_create_allowed(body.scope, resource=_DIMENSION_RESOURCE)
    current_org_id = await resolve_current_org_id(
        db, current_user.user_id, x_organization_id
    )
    org_id, ns_id, ws_id = validate_scope_fks(
        body.scope,
        body.organization_id,
        body.namespace_id,
        workspace_id=body.workspace_id,
        current_org_id=current_org_id,
    )
    await require_permission(
        db,
        current_user.user_id,
        _MANAGE_ATOM,
        organization_id=org_id,
        namespace_id=ns_id,
        workspace_id=ws_id,
    )
    slug = _lower_slug(body.slug or body.name)
    if await _dimension_slug_taken(db, body.scope, org_id, ns_id, ws_id, slug):
        raise ConflictError(
            "knowledge_dimensions.slug_conflict",
            "errors.knowledge_dimensions.slug_conflict",
            f"Knowledge dimension slug '{slug}' already exists in this scope",
        )
    dimension = KnowledgeDimension(
        name=body.name,
        slug=slug,
        description=body.description,
        scope=body.scope,
        organization_id=org_id,
        namespace_id=ns_id,
        workspace_id=ws_id,
    )
    db.add(dimension)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError(
            "knowledge_dimensions.slug_conflict",
            "errors.knowledge_dimensions.slug_conflict",
            f"Knowledge dimension slug '{slug}' already exists in this scope",
        )
    await db.refresh(dimension)
    return dimension


@dimensions_router.patch("/{dimension_id}", response_model=KnowledgeDimensionOut)
async def update_knowledge_dimension(
    dimension_id: str,
    body: KnowledgeDimensionUpdate,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> KnowledgeDimension:
    """Partial-update a knowledge dimension. System rows are read-only."""
    from app.core.scope_guard import ensure_scope_mutable

    current_org_id = await resolve_current_org_id(
        db, current_user.user_id, x_organization_id
    )
    dimension = await _get_active_dimension(db, dimension_id)
    ensure_scope_mutable(dimension.scope, resource=_DIMENSION_RESOURCE, row_id=dimension_id)
    await require_permission(
        db,
        current_user.user_id,
        _MANAGE_ATOM,
        organization_id=dimension.organization_id,
        namespace_id=dimension.namespace_id,
        workspace_id=dimension.workspace_id,
    )
    await _fence_cross_org(
        current_org_id, dimension.scope, dimension.organization_id, dimension_id,
        error_code="knowledge_dimension.not_found",
    )
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "slug" and value is not None:
            value = _lower_slug(value)
        setattr(dimension, field, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError(
            "knowledge_dimensions.slug_conflict",
            "errors.knowledge_dimensions.slug_conflict",
            f"Knowledge dimension slug '{dimension.slug}' already exists in this scope",
        )
    await db.refresh(dimension)
    return dimension


@dimensions_router.delete("/{dimension_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_dimension(
    dimension_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> None:
    """Soft-delete a knowledge dimension. System rows are read-only."""
    from app.core.scope_guard import ensure_scope_mutable

    current_org_id = await resolve_current_org_id(
        db, current_user.user_id, x_organization_id
    )
    dimension = await _get_active_dimension(db, dimension_id)
    ensure_scope_mutable(dimension.scope, resource=_DIMENSION_RESOURCE, row_id=dimension_id)
    await require_permission(
        db,
        current_user.user_id,
        _MANAGE_ATOM,
        organization_id=dimension.organization_id,
        namespace_id=dimension.namespace_id,
        workspace_id=dimension.workspace_id,
    )
    await _fence_cross_org(
        current_org_id, dimension.scope, dimension.organization_id, dimension_id,
        error_code="knowledge_dimension.not_found",
    )
    dimension.soft_delete()
    await db.commit()
