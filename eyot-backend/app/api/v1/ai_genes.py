"""ai_genes CRUD + BaseClass junction attach/detach (PRD-v2).

Routes:
    GET    /api/v1/ai-genes                        — list
    GET    /api/v1/ai-genes/by-slug/{slug}         — get by slug
    GET    /api/v1/ai-genes/{id}                   — get by id
    POST   /api/v1/ai-genes                        — create
    PATCH  /api/v1/ai-genes/{id}                   — update
    DELETE /api/v1/ai-genes/{id}                   — soft-delete
    POST   /api/v1/ai-genes/{id}/attach-base-class — link to BaseClass
    DELETE /api/v1/ai-genes/{id}/attach-base-class/{base_class_id} — unlink
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUserDep, XOrgIdHeader
from app.core.capabilities import build_capabilities_manifest
from app.core.errors import ConflictError, NotFoundError
from app.core.openapi import add_error_responses
from app.core.org_scope import (
    resolve_current_org_id,
    scoped_visibility_clause,
    validate_scope_fks,
)
from app.core.pagination import OffsetPage, paginate_offset
from app.core.permissions import require_permission
from app.models.ai_gene import AiGene, BaseClassAiGene
from app.models.base_class import BaseClass
from app.schemas.ai_gene import (
    AiGeneAttachBaseClassRequest,
    AiGeneCreate,
    AiGeneOut,
    AiGeneUpdate,
    CapabilityInline,
    extract_manifest_capabilities,
)

router = APIRouter(prefix="/ai-genes", tags=["AiGenes"])
add_error_responses(router)


def _manifest_with_capabilities(
    manifest: dict | None,
    capabilities: list[CapabilityInline] | None,
) -> dict | None:
    """Merge a ``capabilities`` entry list into a manifest (v4.9 A2a).

    When ``capabilities`` is provided it becomes ``manifest["capabilities"]``
    via the shared constructor (byte-identical to the combine endpoint's inline
    array); other manifest keys are preserved. When ``capabilities`` is None
    the manifest is returned unchanged — including None.
    """
    if capabilities is None:
        return manifest
    merged = dict(manifest or {})
    merged["capabilities"] = build_capabilities_manifest(capabilities)
    return merged


def _updates_with_capabilities(
    body: AiGeneUpdate, gene: AiGene
) -> dict:
    """Partial-update map with the ``capabilities`` field folded into manifest.

    ``capabilities`` is a request-only field (no column): when present in the
    payload it is serialized into ``manifest["capabilities"]``, taking
    precedence over any manifest passed in the same request.
    """
    updates = body.model_dump(exclude_unset=True)
    caps_present = "capabilities" in updates
    updates.pop("capabilities", None)
    if caps_present:
        base = updates.get("manifest", gene.manifest)
        updates["manifest"] = _manifest_with_capabilities(base, body.capabilities)
    return updates


async def _get_active_gene(db: DB, gene_id: str) -> AiGene:
    gene = await db.get(AiGene, gene_id)
    if gene is None or gene.deleted_at is not None:
        raise NotFoundError(
            "ai_gene.not_found",
            "errors.ai_gene.not_found",
            f"AiGene '{gene_id}' not found",
        )
    return gene


@router.get("", response_model=OffsetPage[AiGeneOut])
async def list_ai_genes(
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
    scope: str | None = Query(None),
    limit: int = 50,
    offset: int = 0,
) -> OffsetPage:
    """Return ai genes visible in the current org context."""
    current_org_id = await resolve_current_org_id(
        db, current_user.user_id, x_organization_id
    )
    stmt = (
        select(AiGene)
        .where(AiGene.deleted_at.is_(None))
        .where(scoped_visibility_clause(AiGene, current_org_id, scope))
        .order_by(AiGene.slug)
    )
    return await paginate_offset(db, stmt, offset, min(limit, 200))


@router.get("/by-slug/{slug}", response_model=AiGeneOut)
async def get_ai_gene_by_slug(
    slug: str,
    db: DB,
    current_user: CurrentUserDep,
) -> AiGene:
    """Return an ai gene by slug."""
    result = await db.execute(
        select(AiGene).where(
            AiGene.slug == slug,
            AiGene.deleted_at.is_(None),
        )
    )
    gene = result.scalar_one_or_none()
    if gene is None:
        raise NotFoundError(
            "ai_gene.not_found",
            "errors.ai_gene.not_found",
            f"AiGene '{slug}' not found",
        )
    return gene


@router.get("/{gene_id}", response_model=AiGeneOut)
async def get_ai_gene(
    gene_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> AiGene:
    """Return an ai gene by id."""
    return await _get_active_gene(db, gene_id)


@router.post("", response_model=AiGeneOut, status_code=status.HTTP_201_CREATED)
async def create_ai_gene(
    body: AiGeneCreate,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> AiGene:
    """Create a new ai gene (requires can_manage_ai_genes)."""
    from app.core.scope_guard import ensure_scope_create_allowed

    ensure_scope_create_allowed(body.scope, resource="ai_gene")
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
        "can_manage_ai_genes",
        organization_id=org_id,
        namespace_id=ns_id,
    )
    existing = await db.execute(
        select(AiGene).where(
            AiGene.slug == body.slug,
            AiGene.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(
            "ai_gene.slug_taken",
            "errors.ai_gene.slug_taken",
            f"AiGene slug '{body.slug}' is already taken",
        )
    gene = AiGene(
        slug=body.slug,
        name=body.name,
        tags=body.tags,
        manifest=_manifest_with_capabilities(body.manifest, body.capabilities),
        description=body.description,
        scope=body.scope,
        organization_id=org_id,
        namespace_id=ns_id,
    )
    db.add(gene)
    await db.commit()
    await db.refresh(gene)
    return gene


@router.patch("/{gene_id}", response_model=AiGeneOut)
async def update_ai_gene(
    gene_id: str,
    body: AiGeneUpdate,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> AiGene:
    """Partial-update an ai gene. Slug and scope are immutable;
    system-scoped presets are read-only (v4.0 D15)."""
    from app.core.scope_guard import ensure_scope_mutable

    current_org_id = await resolve_current_org_id(
        db, current_user.user_id, x_organization_id
    )
    gene = await _get_active_gene(db, gene_id)
    ensure_scope_mutable(gene.scope, resource="ai_gene", row_id=gene_id)
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_ai_genes",
        organization_id=gene.organization_id,
        namespace_id=gene.namespace_id,
    )
    if current_org_id is not None and gene.scope != "system":
        if gene.organization_id != current_org_id:
            raise NotFoundError(
                "ai_gene.not_found",
                "errors.ai_gene.not_found",
                f"AiGene '{gene_id}' not found",
            )
    before_caps = extract_manifest_capabilities(gene.manifest)
    for field, value in _updates_with_capabilities(
        body, gene
    ).items():
        setattr(gene, field, value)
    await db.flush()
    if extract_manifest_capabilities(gene.manifest) != before_caps:
        from app.core.capabilities import bump_entities_for_gene

        await bump_entities_for_gene(db, gene.id)
    await db.commit()
    await db.refresh(gene)
    return gene


@router.delete("/{gene_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ai_gene(
    gene_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> None:
    """Soft-delete an ai gene. System presets are read-only."""
    from app.core.scope_guard import ensure_scope_mutable

    current_org_id = await resolve_current_org_id(
        db, current_user.user_id, x_organization_id
    )
    gene = await _get_active_gene(db, gene_id)
    ensure_scope_mutable(gene.scope, resource="ai_gene", row_id=gene_id)
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_ai_genes",
        organization_id=gene.organization_id,
        namespace_id=gene.namespace_id,
    )
    if current_org_id is not None and gene.scope != "system":
        if gene.organization_id != current_org_id:
            raise NotFoundError(
                "ai_gene.not_found",
                "errors.ai_gene.not_found",
                f"AiGene '{gene_id}' not found",
            )
    gene.soft_delete()
    await db.commit()


@router.post("/{gene_id}/attach-base-class", status_code=status.HTTP_201_CREATED)
async def attach_ai_gene_to_base_class(
    gene_id: str,
    body: AiGeneAttachBaseClassRequest,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> dict[str, str]:
    """Link an ai gene to a BaseClass via junction table."""
    current_org_id = await resolve_current_org_id(
        db, current_user.user_id, x_organization_id
    )
    gene = await _get_active_gene(db, gene_id)
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_ai_genes",
        organization_id=gene.organization_id or current_org_id,
        namespace_id=gene.namespace_id,
    )
    bc = await db.get(BaseClass, body.base_class_id)
    if bc is None or bc.deleted_at is not None:
        raise NotFoundError(
            "base_class.not_found",
            "errors.base_class.not_found",
            f"BaseClass '{body.base_class_id}' not found",
        )
    if bc.scope != "system":
        await require_permission(
            db,
            current_user.user_id,
            "can_manage_ai_genes",
            organization_id=bc.organization_id,
            namespace_id=bc.namespace_id,
        )
    existing = await db.execute(
        select(BaseClassAiGene).where(
            BaseClassAiGene.base_class_id == bc.id,
            BaseClassAiGene.ai_gene_id == gene.id,
            BaseClassAiGene.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        return {
            "base_class_id": bc.id,
            "ai_gene_id": gene.id,
            "status": "already_attached",
        }
    link = BaseClassAiGene(base_class_id=bc.id, ai_gene_id=gene.id)
    db.add(link)
    await db.flush()
    from app.core.capabilities import bump_entities_for_base_class

    await bump_entities_for_base_class(db, bc.slug)
    await db.commit()
    return {"base_class_id": bc.id, "ai_gene_id": gene.id, "status": "attached"}


@router.delete(
    "/{gene_id}/attach-base-class/{base_class_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def detach_ai_gene_from_base_class(
    gene_id: str,
    base_class_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> None:
    """Remove ai gene ↔ BaseClass junction link."""
    current_org_id = await resolve_current_org_id(
        db, current_user.user_id, x_organization_id
    )
    gene = await _get_active_gene(db, gene_id)
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_ai_genes",
        organization_id=gene.organization_id or current_org_id,
        namespace_id=gene.namespace_id,
    )
    bc = await db.get(BaseClass, base_class_id)
    if bc is None or bc.deleted_at is not None:
        raise NotFoundError(
            "base_class.not_found",
            "errors.base_class.not_found",
            f"BaseClass '{base_class_id}' not found",
        )
    if bc.scope != "system":
        await require_permission(
            db,
            current_user.user_id,
            "can_manage_ai_genes",
            organization_id=bc.organization_id,
            namespace_id=bc.namespace_id,
        )
    result = await db.execute(
        select(BaseClassAiGene).where(
            BaseClassAiGene.base_class_id == base_class_id,
            BaseClassAiGene.ai_gene_id == gene_id,
            BaseClassAiGene.deleted_at.is_(None),
        )
    )
    link = result.scalar_one_or_none()
    if link is None:
        raise NotFoundError(
            "ai_gene.not_attached",
            "errors.ai_gene.not_attached",
            f"AiGene '{gene_id}' is not attached to BaseClass '{base_class_id}'",
        )
    link.soft_delete()
    await db.flush()
    from app.core.capabilities import bump_entities_for_base_class

    await bump_entities_for_base_class(db, bc.slug)
    await db.commit()
