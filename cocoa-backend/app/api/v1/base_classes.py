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
from sqlalchemy import and_, or_, select

from app.api.deps import DB, CurrentUserDep
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.openapi import add_error_responses
from app.core.pagination import OffsetPage, paginate_offset
from app.core.permissions import require_super_admin
from app.core.preset_registry import registry
from app.models.base_class import BaseClass
from app.models.base_class_provider_default import BaseClassProviderDefault
from app.models.organization import Organization
from app.models.organization_provider import OrganizationProvider
from app.schemas.base_class import (
    BaseClassCreate,
    BaseClassOut,
    BaseClassUpdate,
    PresetManifestOut,
)
from app.schemas.organization import (
    BaseClassProviderDefaultOut,
    BaseClassProviderDefaultUpdate,
)

router = APIRouter(prefix="/base-classes", tags=["BaseClasses"])
add_error_responses(router)

_INTERNAL_SLUGS = frozenset({"cerebellum-baseclass"})
_INTERNAL_TAGS = frozenset({"internal", "system"})


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
    if include_internal:
        stmt = select(BaseClass).where(BaseClass.deleted_at.is_(None))
    else:
        stmt = select(BaseClass).where(_public_base_class_filter())
    if tag:
        stmt = stmt.where(BaseClass.tags.contains([tag]))
    stmt = stmt.order_by(BaseClass.created_at.desc())
    return await paginate_offset(db, stmt, offset, min(limit, 200))


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

    manifest_data = preset.manifest if isinstance(preset.manifest, dict) else {}
    return BaseClassOut(
        id=preset.id,
        slug=preset.slug,
        name=preset.name,
        display_name=preset.display_name,
        description=preset.description,
        version=preset.version,
        tags=preset.tags,
        manifest=PresetManifestOut.model_validate(manifest_data),
        created_at=preset.created_at,
        updated_at=preset.updated_at,
    )


@router.post("", response_model=BaseClassOut, status_code=status.HTTP_201_CREATED)
async def create_base_class(
    body: BaseClassCreate,
    db: DB,
    current_user: CurrentUserDep,
) -> BaseClass:
    """Create a new base class. Raises 409 on active slug conflict."""
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
        manifest=body.manifest,
        display_name=body.display_name,
        description=body.description,
        tags=body.tags,
    )
    db.add(preset)
    await db.commit()
    await db.refresh(preset)

    await registry.reload(db)
    return preset


@router.patch("/{preset_id}", response_model=BaseClassOut)
async def update_base_class(
    preset_id: str,
    body: BaseClassUpdate,
    db: DB,
    current_user: CurrentUserDep,
) -> BaseClass:
    """Partial-update an existing base class. Slug is immutable."""
    preset = await db.get(BaseClass, preset_id)
    if preset is None or preset.deleted_at is not None:
        raise NotFoundError(
            "base_class.not_found",
            "errors.base_class.not_found",
            f"BaseClass '{preset_id}' not found",
        )

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(preset, field, value)

    await db.commit()
    await db.refresh(preset)

    await registry.reload(db)
    return preset


@router.delete("/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_base_class(
    preset_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> None:
    """Soft-delete a base class."""
    preset = await db.get(BaseClass, preset_id)
    if preset is None or preset.deleted_at is not None:
        raise NotFoundError(
            "base_class.not_found",
            "errors.base_class.not_found",
            f"BaseClass '{preset_id}' not found",
        )

    preset.soft_delete()
    await db.commit()

    await registry.reload(db)
