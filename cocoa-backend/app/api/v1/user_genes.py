"""user_genes admin CRUD + user attach/detach (PRD-v2).

Routes (super-admin for mutations):
    GET    /api/v1/user-genes              — list
    GET    /api/v1/user-genes/by-slug/{slug} — get by slug
    GET    /api/v1/user-genes/{id}         — get by id
    POST   /api/v1/user-genes              — create
    PATCH  /api/v1/user-genes/{id}         — update
    DELETE /api/v1/user-genes/{id}         — soft-delete
    POST   /api/v1/user-genes/{id}/attach  — attach to user
    DELETE /api/v1/user-genes/{id}/attach/{user_id} — detach from user
"""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUserDep, XOrgIdHeader
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.gene_atoms import ATOM_CATALOG, ensure_atom_genes
from app.core.openapi import add_error_responses
from app.core.org_scope import resolve_current_org_id
from app.core.pagination import OffsetPage, paginate_offset
from app.core.permissions import require_permission
from app.models.user import User
from app.models.user_gene import UserGene, UserGeneKind, UserUserGene
from app.schemas.user_gene import (
    UserGeneAttachRequest,
    UserGeneCreate,
    UserGeneOut,
    UserGeneUpdate,
)

router = APIRouter(prefix="/user-genes", tags=["UserGenes"])
add_error_responses(router)


async def _get_active_gene(db: DB, gene_id: str) -> UserGene:
    gene = await db.get(UserGene, gene_id)
    if gene is None or gene.deleted_at is not None:
        raise NotFoundError(
            "user_gene.not_found",
            "errors.user_gene.not_found",
            f"UserGene '{gene_id}' not found",
        )
    return gene


async def _require_manage_genes(
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: str | None,
) -> str | None:
    """Resolve org context and require can_manage_genes (non-super-admin)."""
    org_id = await resolve_current_org_id(
        db, current_user.user_id, x_organization_id
    )
    if current_user.is_super_admin:
        return org_id
    if org_id is None:
        raise ForbiddenError(
            "organization.context_required",
            "errors.organization.context_required",
            "Organization context is required (X-Organization-Id or a single org contract)",
        )
    await require_permission(
        db, current_user.user_id, "can_manage_genes", organization_id=org_id
    )
    return org_id


@router.get("/permission-keys")
async def list_permission_keys(
    current_user: CurrentUserDep,
) -> dict[str, list[str]]:
    """Known atomic can_* slugs for gene editor checkboxes."""
    return {"items": sorted(ATOM_CATALOG)}


@router.get("", response_model=OffsetPage[UserGeneOut])
async def list_user_genes(
    db: DB,
    current_user: CurrentUserDep,
    limit: int = 50,
    offset: int = 0,
) -> OffsetPage:
    """Return all active user genes (any authenticated user may list)."""
    # Ensure atomic can_* genes exist (idempotent).
    await ensure_atom_genes(db)
    await db.commit()
    stmt = (
        select(UserGene)
        .where(UserGene.deleted_at.is_(None))
        .order_by(UserGene.slug)
    )
    return await paginate_offset(db, stmt, offset, min(limit, 200))


@router.get("/by-slug/{slug}", response_model=UserGeneOut)
async def get_user_gene_by_slug(
    slug: str,
    db: DB,
    current_user: CurrentUserDep,
) -> UserGene:
    """Return a user gene by its slug."""
    result = await db.execute(
        select(UserGene).where(
            UserGene.slug == slug,
            UserGene.deleted_at.is_(None),
        )
    )
    gene = result.scalar_one_or_none()
    if gene is None:
        raise NotFoundError(
            "user_gene.not_found",
            "errors.user_gene.not_found",
            f"UserGene '{slug}' not found",
        )
    return gene


@router.get("/{gene_id}", response_model=UserGeneOut)
async def get_user_gene(
    gene_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> UserGene:
    """Return a user gene by id."""
    return await _get_active_gene(db, gene_id)


@router.post("", response_model=UserGeneOut, status_code=status.HTTP_201_CREATED)
async def create_user_gene(
    body: UserGeneCreate,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> UserGene:
    """Create a custom user gene (requires can_manage_genes)."""
    await _require_manage_genes(db, current_user, x_organization_id)
    existing = await db.execute(
        select(UserGene).where(
            UserGene.slug == body.slug,
            UserGene.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(
            "user_gene.slug_taken",
            "errors.user_gene.slug_taken",
            f"UserGene slug '{body.slug}' is already taken",
        )
    gene = UserGene(
        slug=body.slug,
        name=body.name,
        kind=body.kind,
        effect_scope=body.effect_scope,
        description=body.description,
    )
    db.add(gene)
    await db.commit()
    await db.refresh(gene)
    return gene


@router.patch("/{gene_id}", response_model=UserGeneOut)
async def update_user_gene(
    gene_id: str,
    body: UserGeneUpdate,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> UserGene:
    """Update a user gene. Builtin genes cannot change slug/kind."""
    await _require_manage_genes(db, current_user, x_organization_id)
    gene = await _get_active_gene(db, gene_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(gene, field, value)
    await db.commit()
    await db.refresh(gene)
    return gene


@router.delete("/{gene_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_gene(
    gene_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> None:
    """Soft-delete a user gene. Builtin presets cannot be deleted."""
    await _require_manage_genes(db, current_user, x_organization_id)
    gene = await _get_active_gene(db, gene_id)
    if gene.kind == UserGeneKind.builtin.value:
        raise ConflictError(
            "user_gene.cannot_delete_builtin",
            "errors.user_gene.cannot_delete_builtin",
            f"Builtin UserGene '{gene.slug}' cannot be deleted",
        )
    gene.soft_delete()
    await db.commit()


@router.post("/{gene_id}/attach", status_code=status.HTTP_201_CREATED)
async def attach_user_gene(
    gene_id: str,
    body: UserGeneAttachRequest,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> dict[str, str]:
    """Attach a user gene to a user (requires can_manage_genes). Idempotent."""
    await _require_manage_genes(db, current_user, x_organization_id)
    gene = await _get_active_gene(db, gene_id)
    user = await db.get(User, body.user_id)
    if user is None or user.deleted_at is not None:
        raise NotFoundError(
            "auth.user_not_found",
            "errors.auth.user_not_found",
            f"User '{body.user_id}' not found",
        )
    existing = await db.execute(
        select(UserUserGene).where(
            UserUserGene.user_id == body.user_id,
            UserUserGene.user_gene_id == gene.id,
            UserUserGene.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        return {"user_id": body.user_id, "user_gene_id": gene.id, "status": "already_attached"}

    link = UserUserGene(user_id=body.user_id, user_gene_id=gene.id)
    db.add(link)
    await db.commit()
    return {"user_id": body.user_id, "user_gene_id": gene.id, "status": "attached"}


@router.delete("/{gene_id}/attach/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def detach_user_gene(
    gene_id: str,
    user_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> None:
    """Detach a user gene from a user."""
    await _require_manage_genes(db, current_user, x_organization_id)
    await _get_active_gene(db, gene_id)
    result = await db.execute(
        select(UserUserGene).where(
            UserUserGene.user_id == user_id,
            UserUserGene.user_gene_id == gene_id,
            UserUserGene.deleted_at.is_(None),
        )
    )
    link = result.scalar_one_or_none()
    if link is None:
        raise NotFoundError(
            "user_gene.not_attached",
            "errors.user_gene.not_attached",
            f"UserGene '{gene_id}' is not attached to user '{user_id}'",
        )
    link.soft_delete()
    await db.commit()
