"""BaseClass CRUD API routes (PRD-v2 — sole source for 神职 templates).

Routes (all require authentication):
    GET    /api/v1/base-classes          — List active base classes
    GET    /api/v1/base-classes/{slug}   — Get by slug (manifest expanded)
    POST   /api/v1/base-classes          — Create
    PATCH  /api/v1/base-classes/{id}     — Update
    DELETE /api/v1/base-classes/{id}     — Soft-delete
    GET/PATCH /api/v1/base-classes/by-id/{id}/provider-default
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, or_, select

from app.api.deps import DB, CurrentUserDep, XOrgIdHeader
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.openapi import add_error_responses
from app.core.org_scope import (
    resolve_current_org_id,
    scoped_visibility_clause,
    validate_scope_fks,
)
from app.core.pagination import OffsetPage, paginate_offset
from app.core.permissions import require_permission, require_super_admin
from app.core.preset_registry import registry
from app.models.ai_gene import AiGene
from app.models.base_class import BaseClass
from app.models.base_class_provider_default import BaseClassProviderDefault
from app.models.capability_market import CapabilityMarketEntry
from app.models.organization import Organization
from app.models.organization_provider import OrganizationProvider
from app.schemas.base_class import (
    BaseClassCreate,
    BaseClassOut,
    BaseClassUpdate,
)
from app.schemas.organization import (
    BaseClassProviderDefaultOut,
    BaseClassProviderDefaultUpdate,
)

router = APIRouter(prefix="/base-classes", tags=["BaseClasses"])
add_error_responses(router)

_INTERNAL_SLUGS = frozenset({"cerebellum-baseclass"})
_INTERNAL_TAGS = frozenset({"internal", "system"})


class BaseClassCapabilityAttachBody(BaseModel):
    capability_id: str


class BaseClassAiGeneAttachBody(BaseModel):
    ai_gene_id: str

# Manifest mirror keys — read-only aggregates filled from junction rows;
# never a write truth (v4.0 migration-spec §1 aggregate read path).
_MIRROR_KEYS = ("skills", "tools", "commands")


def _strip_manifest_mirror(manifest: dict | None) -> dict | None:
    """Drop mirror arrays from an incoming manifest (write-path strip)."""
    if not isinstance(manifest, dict):
        return manifest
    return {k: v for k, v in manifest.items() if k not in _MIRROR_KEYS}


async def _base_class_out(db: DB, preset: BaseClass) -> BaseClassOut:
    """Serialize a BaseClass with the manifest mirror filled from junctions."""
    from app.core.capabilities import (
        load_base_class_capability_dicts,
        mirror_arrays,
    )

    manifest = dict(preset.manifest) if isinstance(preset.manifest, dict) else {}
    cap_dicts = await load_base_class_capability_dicts(db, preset.id)
    manifest.update(mirror_arrays(cap_dicts))
    return BaseClassOut(
        id=preset.id,
        slug=preset.slug,
        name=preset.name,
        display_name=preset.display_name,
        description=preset.description,
        version=preset.version,
        tags=preset.tags,
        has_knowledge=preset.has_knowledge,
        scope=preset.scope,
        organization_id=preset.organization_id,
        namespace_id=preset.namespace_id,
        manifest=manifest,
        created_at=preset.created_at,
        updated_at=preset.updated_at,
    )


def _public_base_class_filter():
    """Exclude internal/system 神职 from market / onboarding lists."""
    tag_clauses = [
        ~BaseClass.tags.contains([tag]) for tag in sorted(_INTERNAL_TAGS)
    ]
    return and_(
        BaseClass.deleted_at.is_(None),
        BaseClass.slug.notin_(_INTERNAL_SLUGS),
        or_(BaseClass.tags.is_(None), and_(*tag_clauses)),
    )


@router.get("", response_model=OffsetPage[BaseClassOut])
async def list_base_classes(
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
    scope: str | None = Query(None),
    limit: int = 50,
    offset: int = 0,
    include_internal: bool = Query(
        default=False,
        description="When true, include cerebellum-baseclass / internal tags",
    ),
    tag: str | None = Query(
        default=None,
        description="Optional tag filter (e.g. ultraworker)",
    ),
) -> OffsetPage:
    """Return a paginated list of active (non-deleted) base classes."""
    current_org_id = await resolve_current_org_id(
        db, current_user.user_id, x_organization_id
    )
    visibility = scoped_visibility_clause(BaseClass, current_org_id, scope)
    if include_internal:
        stmt = select(BaseClass).where(
            BaseClass.deleted_at.is_(None),
            visibility,
        )
    else:
        stmt = select(BaseClass).where(
            and_(_public_base_class_filter(), visibility),
        )
    if tag:
        stmt = stmt.where(BaseClass.tags.contains([tag]))
    stmt = stmt.order_by(BaseClass.created_at.desc())
    page = await paginate_offset(db, stmt, offset, min(limit, 200))
    items = [await _base_class_out(db, bc) for bc in page.items]
    return OffsetPage(
        items=items,
        offset=page.offset,
        limit=page.limit,
        total=page.total,
    )


@router.get(
    "/by-id/{preset_id}/provider-default",
    response_model=BaseClassProviderDefaultOut | None,
)
async def get_provider_default(
    preset_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> BaseClassProviderDefault | None:
    preset = await db.get(BaseClass, preset_id)
    if preset is None or preset.deleted_at is not None:
        raise NotFoundError(
            "base_class.not_found",
            "errors.base_class.not_found",
            f"BaseClass '{preset_id}' not found",
        )
    result = await db.execute(
        select(BaseClassProviderDefault).where(
            BaseClassProviderDefault.base_class_id == preset_id,
            BaseClassProviderDefault.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


@router.patch(
    "/by-id/{preset_id}/provider-default",
    response_model=BaseClassProviderDefaultOut,
)
async def update_provider_default(
    preset_id: str,
    body: BaseClassProviderDefaultUpdate,
    db: DB,
    current_user: CurrentUserDep,
) -> BaseClassProviderDefault:
    require_super_admin(current_user)
    preset = await db.get(BaseClass, preset_id)
    if preset is None or preset.deleted_at is not None:
        raise NotFoundError(
            "base_class.not_found",
            "errors.base_class.not_found",
            f"BaseClass '{preset_id}' not found",
        )

    data = body.model_dump(exclude_unset=True)
    if "provider_id" in data and data["provider_id"] is not None:
        org = await db.execute(
            select(Organization).where(
                Organization.slug == "default",
                Organization.deleted_at.is_(None),
            )
        )
        org_row = org.scalar_one_or_none()
        if org_row is None:
            raise NotFoundError(
                "organization.not_found",
                "errors.organization.not_found",
                "Default organization not found",
            )
        prov = await db.execute(
            select(OrganizationProvider).where(
                OrganizationProvider.id == data["provider_id"],
                OrganizationProvider.organization_id == org_row.id,
                OrganizationProvider.deleted_at.is_(None),
            )
        )
        if prov.scalar_one_or_none() is None:
            raise NotFoundError(
                "organization_provider.not_found",
                "errors.organization_provider.not_found",
                f"OrganizationProvider '{data['provider_id']}' not found",
            )

    result = await db.execute(
        select(BaseClassProviderDefault).where(
            BaseClassProviderDefault.base_class_id == preset_id,
            BaseClassProviderDefault.deleted_at.is_(None),
        )
    )
    binding = result.scalar_one_or_none()

    provider_id = data.get("provider_id", binding.provider_id if binding else None)
    model = data.get("model", binding.model if binding else None)

    if not provider_id or not model:
        raise ValidationError(
            "base_class_provider_default.incomplete",
            "errors.base_class_provider_default.incomplete",
            "provider_id and model are required",
        )

    if binding is None:
        binding = BaseClassProviderDefault(
            base_class_id=preset_id,
            provider_id=provider_id,
            model=model,
        )
        db.add(binding)
    else:
        binding.provider_id = provider_id
        binding.model = model

    await db.commit()
    await db.refresh(binding)
    return binding


@router.post(
    "/{preset_id}/capabilities",
    status_code=status.HTTP_201_CREATED,
)
async def attach_base_class_capability(
    preset_id: str,
    body: BaseClassCapabilityAttachBody,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> dict[str, str]:
    """Attach a capability to a base class."""
    from app.core.capabilities import (
        attach_base_class_capability,
        bump_entities_for_base_class,
    )

    preset = await db.get(BaseClass, preset_id)
    if preset is None or preset.deleted_at is not None:
        raise NotFoundError(
            "base_class.not_found",
            "errors.base_class.not_found",
            f"BaseClass '{preset_id}' not found",
        )
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_capabilities",
        organization_id=preset.organization_id,
        namespace_id=preset.namespace_id,
    )
    cap = await db.get(CapabilityMarketEntry, body.capability_id)
    if cap is None or cap.deleted_at is not None:
        raise NotFoundError(
            "capability_market.not_found",
            "errors.capability_market.not_found",
            f"Capability '{body.capability_id}' not found",
        )
    if cap.scope != "system":
        await require_permission(
            db,
            current_user.user_id,
            "can_manage_capabilities",
            organization_id=cap.organization_id,
            namespace_id=cap.namespace_id,
        )
    await attach_base_class_capability(
        db, base_class_id=preset_id, capability_id=body.capability_id
    )
    await bump_entities_for_base_class(db, preset.slug)
    await db.commit()
    return {"base_class_id": preset_id, "capability_id": body.capability_id}


@router.delete(
    "/{preset_id}/capabilities/{capability_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def detach_base_class_capability_route(
    preset_id: str,
    capability_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> None:
    """Detach a capability from a base class (soft-delete junction)."""
    from app.core.capabilities import (
        bump_entities_for_base_class,
        detach_base_class_capability,
    )

    preset = await db.get(BaseClass, preset_id)
    if preset is None or preset.deleted_at is not None:
        raise NotFoundError(
            "base_class.not_found",
            "errors.base_class.not_found",
            f"BaseClass '{preset_id}' not found",
        )
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_capabilities",
        organization_id=preset.organization_id,
        namespace_id=preset.namespace_id,
    )
    cap = await db.get(CapabilityMarketEntry, capability_id)
    if cap is None or cap.deleted_at is not None:
        raise NotFoundError(
            "capability_market.not_found",
            "errors.capability_market.not_found",
            f"Capability '{capability_id}' not found",
        )
    if cap.scope != "system":
        await require_permission(
            db,
            current_user.user_id,
            "can_manage_capabilities",
            organization_id=cap.organization_id,
            namespace_id=cap.namespace_id,
        )
    await detach_base_class_capability(
        db, base_class_id=preset_id, capability_id=capability_id
    )
    await bump_entities_for_base_class(db, preset.slug)
    await db.commit()


@router.post(
    "/{preset_id}/ai-genes",
    status_code=status.HTTP_201_CREATED,
)
async def attach_base_class_ai_gene_route(
    preset_id: str,
    body: BaseClassAiGeneAttachBody,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> dict[str, str]:
    """Attach an ai gene to a base class."""
    from app.core.capabilities import (
        attach_base_class_ai_gene,
        bump_entities_for_base_class,
    )

    preset = await db.get(BaseClass, preset_id)
    if preset is None or preset.deleted_at is not None:
        raise NotFoundError(
            "base_class.not_found",
            "errors.base_class.not_found",
            f"BaseClass '{preset_id}' not found",
        )
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_ai_genes",
        organization_id=preset.organization_id,
        namespace_id=preset.namespace_id,
    )
    gene = await db.get(AiGene, body.ai_gene_id)
    if gene is None or gene.deleted_at is not None:
        raise NotFoundError(
            "ai_gene.not_found",
            "errors.ai_gene.not_found",
            f"AiGene '{body.ai_gene_id}' not found",
        )
    if gene.scope != "system":
        await require_permission(
            db,
            current_user.user_id,
            "can_manage_ai_genes",
            organization_id=gene.organization_id,
            namespace_id=gene.namespace_id,
        )
    await attach_base_class_ai_gene(
        db, base_class_id=preset_id, ai_gene_id=body.ai_gene_id
    )
    await bump_entities_for_base_class(db, preset.slug)
    await db.commit()
    return {"base_class_id": preset_id, "ai_gene_id": body.ai_gene_id}


@router.delete(
    "/{preset_id}/ai-genes/{ai_gene_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def detach_base_class_ai_gene_route(
    preset_id: str,
    ai_gene_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> None:
    """Detach an ai gene from a base class."""
    from app.core.capabilities import (
        bump_entities_for_base_class,
        detach_base_class_ai_gene,
    )

    preset = await db.get(BaseClass, preset_id)
    if preset is None or preset.deleted_at is not None:
        raise NotFoundError(
            "base_class.not_found",
            "errors.base_class.not_found",
            f"BaseClass '{preset_id}' not found",
        )
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_ai_genes",
        organization_id=preset.organization_id,
        namespace_id=preset.namespace_id,
    )
    gene = await db.get(AiGene, ai_gene_id)
    if gene is None or gene.deleted_at is not None:
        raise NotFoundError(
            "ai_gene.not_found",
            "errors.ai_gene.not_found",
            f"AiGene '{ai_gene_id}' not found",
        )
    if gene.scope != "system":
        await require_permission(
            db,
            current_user.user_id,
            "can_manage_ai_genes",
            organization_id=gene.organization_id,
            namespace_id=gene.namespace_id,
        )
    await detach_base_class_ai_gene(
        db, base_class_id=preset_id, ai_gene_id=ai_gene_id
    )
    await bump_entities_for_base_class(db, preset.slug)
    await db.commit()


@router.get("/{slug}", response_model=BaseClassOut)
async def get_base_class_by_slug(
    slug: str,
    db: DB,
    current_user: CurrentUserDep,
) -> BaseClassOut:
    """Return a single base class by slug with expanded manifest."""
    result = await db.execute(
        select(BaseClass).where(
            BaseClass.slug == slug,
            BaseClass.deleted_at.is_(None),
        )
    )
    preset = result.scalar_one_or_none()
    if preset is None:
        raise NotFoundError(
            "base_class.not_found",
            "errors.base_class.not_found",
            f"BaseClass '{slug}' not found",
        )

    return await _base_class_out(db, preset)


@router.post("", response_model=BaseClassOut, status_code=status.HTTP_201_CREATED)
async def create_base_class(
    body: BaseClassCreate,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> BaseClassOut:
    """Create a new base class. Raises 409 on active slug conflict.

    v4.0 D15: new rows default to ``scope=org``; ``scope=system`` is preset-only.
    Manifest mirror arrays are stripped on write.
    """
    from app.core.scope_guard import ensure_scope_create_allowed

    ensure_scope_create_allowed(body.scope, resource="base_class")
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
        "can_manage_organization",
        organization_id=org_id,
        namespace_id=ns_id,
    )
    existing = await db.execute(
        select(BaseClass).where(
            BaseClass.slug == body.slug,
            BaseClass.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(
            "base_class.slug_taken",
            "errors.base_class.slug_taken",
            f"BaseClass slug '{body.slug}' is already taken",
        )

    preset = BaseClass(
        slug=body.slug,
        name=body.name,
        version=body.version,
        manifest=_strip_manifest_mirror(body.manifest),
        has_knowledge=body.has_knowledge,
        display_name=body.display_name,
        description=body.description,
        tags=body.tags,
        scope=body.scope,
        organization_id=org_id,
        namespace_id=ns_id,
    )
    db.add(preset)
    await db.commit()
    await db.refresh(preset)

    await registry.reload(db)
    return await _base_class_out(db, preset)


@router.patch("/{preset_id}", response_model=BaseClassOut)
async def update_base_class(
    preset_id: str,
    body: BaseClassUpdate,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> BaseClassOut:
    """Partial-update an existing base class. Slug and scope are immutable;
    system-scoped presets are read-only (v4.0 D15)."""
    from app.core.scope_guard import ensure_scope_mutable

    current_org_id = await resolve_current_org_id(
        db, current_user.user_id, x_organization_id
    )
    preset = await db.get(BaseClass, preset_id)
    if preset is None or preset.deleted_at is not None:
        raise NotFoundError(
            "base_class.not_found",
            "errors.base_class.not_found",
            f"BaseClass '{preset_id}' not found",
        )
    ensure_scope_mutable(preset.scope, resource="base_class", row_id=preset_id)
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_organization",
        organization_id=preset.organization_id,
        namespace_id=preset.namespace_id,
    )
    if current_org_id is not None and preset.scope != "system":
        if preset.organization_id != current_org_id:
            raise NotFoundError(
                "base_class.not_found",
                "errors.base_class.not_found",
                f"BaseClass '{preset_id}' not found",
            )

    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "manifest":
            value = _strip_manifest_mirror(value)
        setattr(preset, field, value)

    await db.commit()
    await db.refresh(preset)

    await registry.reload(db)
    return await _base_class_out(db, preset)


@router.delete("/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_base_class(
    preset_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> None:
    """Soft-delete a base class. System-scoped presets are read-only (D15)."""
    from app.core.scope_guard import ensure_scope_mutable

    current_org_id = await resolve_current_org_id(
        db, current_user.user_id, x_organization_id
    )
    preset = await db.get(BaseClass, preset_id)
    if preset is None or preset.deleted_at is not None:
        raise NotFoundError(
            "base_class.not_found",
            "errors.base_class.not_found",
            f"BaseClass '{preset_id}' not found",
        )
    ensure_scope_mutable(preset.scope, resource="base_class", row_id=preset_id)
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_organization",
        organization_id=preset.organization_id,
        namespace_id=preset.namespace_id,
    )
    if current_org_id is not None and preset.scope != "system":
        if preset.organization_id != current_org_id:
            raise NotFoundError(
                "base_class.not_found",
                "errors.base_class.not_found",
                f"BaseClass '{preset_id}' not found",
            )

    preset.soft_delete()
    await db.commit()

    await registry.reload(db)
