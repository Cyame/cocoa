"""Capability market CRUD (L1) — v4.1 independent routes."""

from __future__ import annotations

from fastapi import APIRouter, Query, status
from sqlalchemy import select

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
from app.core.scope_guard import ensure_scope_create_allowed, ensure_scope_mutable
from app.models.capability_market import (
    CapabilityCreatedVia,
    CapabilityMarketEntry,
)
from app.schemas.capability_market import (
    CapabilityMarketEntryCreate,
    CapabilityMarketEntryOut,
    CapabilityMarketEntryUpdate,
)

router = APIRouter(prefix="/capability-market", tags=["CapabilityMarket"])
add_error_responses(router)


async def _get_active_entry(db: DB, entry_id: str) -> CapabilityMarketEntry:
    entry = await db.get(CapabilityMarketEntry, entry_id)
    if entry is None or entry.deleted_at is not None:
        raise NotFoundError(
            "capability_market.not_found",
            "errors.capability_market.not_found",
            f"Capability market entry '{entry_id}' not found",
        )
    return entry


def capability_market_list_stmt(
    *,
    current_org_id: str | None,
    scope: str | None,
    cap_type: str | None,
    tag: str | None,
    created_via: str | None,
):
    """Shared list query for capability market (used by GET)."""
    stmt = (
        select(CapabilityMarketEntry)
        .where(CapabilityMarketEntry.deleted_at.is_(None))
        .where(scoped_visibility_clause(CapabilityMarketEntry, current_org_id, scope))
        .order_by(CapabilityMarketEntry.name)
    )
    if cap_type is not None:
        stmt = stmt.where(CapabilityMarketEntry.type == cap_type)
    if created_via is not None:
        stmt = stmt.where(CapabilityMarketEntry.created_via == created_via)
    if tag is not None:
        stmt = stmt.where(CapabilityMarketEntry.tags.contains([tag]))
    return stmt


@router.get("", response_model=OffsetPage[CapabilityMarketEntryOut])
async def list_capability_market(
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
    scope: str | None = Query(None),
    type: str | None = Query(None, alias="type"),
    tag: str | None = Query(None),
    created_via: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> OffsetPage:
    """List capability market entries visible in the current org context."""
    current_org_id = await resolve_current_org_id(
        db, current_user.user_id, x_organization_id
    )
    stmt = capability_market_list_stmt(
        current_org_id=current_org_id,
        scope=scope,
        cap_type=type,
        tag=tag,
        created_via=created_via,
    )
    return await paginate_offset(db, stmt, offset, limit)


@router.get("/{entry_id}", response_model=CapabilityMarketEntryOut)
async def get_capability_market_entry(
    entry_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> CapabilityMarketEntry:
    """Return one capability market entry if visible to the caller."""
    current_org_id = await resolve_current_org_id(
        db, current_user.user_id, x_organization_id
    )
    entry = await _get_active_entry(db, entry_id)
    visible = scoped_visibility_clause(
        CapabilityMarketEntry, current_org_id, None
    )
    check = await db.execute(
        select(CapabilityMarketEntry.id).where(
            CapabilityMarketEntry.id == entry_id,
            CapabilityMarketEntry.deleted_at.is_(None),
            visible,
        )
    )
    if check.scalar_one_or_none() is None:
        raise NotFoundError(
            "capability_market.not_found",
            "errors.capability_market.not_found",
            f"Capability market entry '{entry_id}' not found",
        )
    return entry


@router.post("", response_model=CapabilityMarketEntryOut, status_code=status.HTTP_201_CREATED)
async def create_capability_market_entry(
    body: CapabilityMarketEntryCreate,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> CapabilityMarketEntry:
    """Create a capability market entry (requires can_manage_capabilities)."""
    ensure_scope_create_allowed(body.scope, resource="capability_market")
    current_org_id = await resolve_current_org_id(
        db, current_user.user_id, x_organization_id
    )
    org_id, ns_id, _ = validate_scope_fks(
        body.scope,
        body.organization_id,
        body.namespace_id,
        current_org_id=current_org_id,
    )
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_capabilities",
        organization_id=org_id,
        namespace_id=ns_id,
    )

    existing = await db.execute(
        select(CapabilityMarketEntry).where(
            CapabilityMarketEntry.name == body.name,
            CapabilityMarketEntry.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(
            "capability_market.name_taken",
            "errors.capability_market.name_taken",
            f"Capability name '{body.name}' is already taken",
        )

    entry = CapabilityMarketEntry(
        name=body.name,
        type=body.type,
        scope=body.scope,
        organization_id=org_id,
        namespace_id=ns_id,
        description=body.description,
        config_template=body.config_template,
        required_knowledge=body.required_knowledge,
        tags=body.tags,
        created_via=CapabilityCreatedVia.manual.value,
        created_by_user_id=current_user.user_id,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.patch("/{entry_id}", response_model=CapabilityMarketEntryOut)
async def update_capability_market_entry(
    entry_id: str,
    body: CapabilityMarketEntryUpdate,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> CapabilityMarketEntry:
    """Update a capability market entry."""
    current_org_id = await resolve_current_org_id(
        db, current_user.user_id, x_organization_id
    )
    entry = await _get_active_entry(db, entry_id)
    ensure_scope_mutable(entry.scope, resource="capability_market", row_id=entry_id)
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_capabilities",
        organization_id=entry.organization_id,
        namespace_id=entry.namespace_id,
    )
    if current_org_id is not None and entry.scope != "system":
        if entry.organization_id != current_org_id:
            raise NotFoundError(
                "capability_market.not_found",
                "errors.capability_market.not_found",
                f"Capability market entry '{entry_id}' not found",
            )

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_capability_market_entry(
    entry_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> None:
    """Soft-delete a capability market entry."""
    current_org_id = await resolve_current_org_id(
        db, current_user.user_id, x_organization_id
    )
    entry = await _get_active_entry(db, entry_id)
    ensure_scope_mutable(entry.scope, resource="capability_market", row_id=entry_id)
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_capabilities",
        organization_id=entry.organization_id,
        namespace_id=entry.namespace_id,
    )
    if current_org_id is not None and entry.scope != "system":
        if entry.organization_id != current_org_id:
            raise NotFoundError(
                "capability_market.not_found",
                "errors.capability_market.not_found",
                f"Capability market entry '{entry_id}' not found",
            )
    entry.soft_delete()
    await db.commit()
