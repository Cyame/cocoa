"""EmployeePreset CRUD API routes.

Endpoints for managing agent preset templates (灵格).  All mutations
(create, update, delete) refresh the in-memory :class:`PresetRegistry`
cache so that subsequent lookups see the new state immediately.

Routes (all require authentication):
    GET    /api/v1/employee-presets          — List all active presets (offset page)
    GET    /api/v1/employee-presets/{slug}   — Get a single preset by slug (manifest expanded)
    POST   /api/v1/employee-presets          — Create a new preset
    PATCH  /api/v1/employee-presets/{id}     — Update an existing preset
    DELETE /api/v1/employee-presets/{id}     — Soft-delete a preset
"""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUserDep
from app.core.errors import ConflictError, NotFoundError
from app.core.openapi import add_error_responses
from app.core.pagination import OffsetPage, paginate_offset
from app.core.preset_registry import registry
from app.models.employee import EmployeePreset
from app.schemas.employee_preset import (
    EmployeePresetCreate,
    EmployeePresetOut,
    EmployeePresetUpdate,
    PresetManifestOut,
)

router = APIRouter(prefix="/employee-presets", tags=["EmployeePresets"])
add_error_responses(router)


@router.get("", response_model=OffsetPage[EmployeePresetOut])
async def list_presets(
    db: DB,
    current_user: CurrentUserDep,
    limit: int = 50,
    offset: int = 0,
) -> OffsetPage:
    """Return a paginated list of active (non-deleted) presets."""
    stmt = select(EmployeePreset).where(EmployeePreset.deleted_at.is_(None)).order_by(EmployeePreset.created_at)
    return await paginate_offset(db, stmt, offset, min(limit, 200))


@router.get("/{slug}", response_model=EmployeePresetOut)
async def get_preset_by_slug(
    slug: str,
    db: DB,
    current_user: CurrentUserDep,
) -> EmployeePresetOut:
    """Return a single preset by slug.  Manifest is materialised as ``PresetManifestOut``."""
    result = await db.execute(
        select(EmployeePreset).where(
            EmployeePreset.slug == slug,
            EmployeePreset.deleted_at.is_(None),
        )
    )
    preset = result.scalar_one_or_none()
    if preset is None:
        raise NotFoundError(
            "employee_preset.not_found",
            "errors.employee_preset.not_found",
            f"EmployeePreset '{slug}' not found",
        )

    manifest_data = preset.manifest if isinstance(preset.manifest, dict) else {}
    return EmployeePresetOut(
        id=preset.id,
        slug=preset.slug,
        name=preset.name,
        version=preset.version,
        manifest=PresetManifestOut.model_validate(manifest_data),
        created_at=preset.created_at,
        updated_at=preset.updated_at,
    )


@router.post("", response_model=EmployeePresetOut, status_code=status.HTTP_201_CREATED)
async def create_preset(
    body: EmployeePresetCreate,
    db: DB,
    current_user: CurrentUserDep,
) -> EmployeePreset:
    """Create a new preset.

    Raises 409 if a preset with the same slug already exists (active).
    Refreshes the registry cache after creation.
    """
    existing = await db.execute(
        select(EmployeePreset).where(
            EmployeePreset.slug == body.slug,
            EmployeePreset.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(
            "employee_preset.slug_taken",
            "errors.employee_preset.slug_taken",
            f"Preset slug '{body.slug}' is already taken",
        )

    preset = EmployeePreset(
        slug=body.slug,
        name=body.name,
        version=body.version,
        manifest=body.manifest,
    )
    db.add(preset)
    await db.commit()
    await db.refresh(preset)

    await registry.reload(db)
    return preset


@router.patch("/{preset_id}", response_model=EmployeePresetOut)
async def update_preset(
    preset_id: str,
    body: EmployeePresetUpdate,
    db: DB,
    current_user: CurrentUserDep,
) -> EmployeePreset:
    """Update an existing preset.

    Only the fields provided in the request body are updated (partial update).
    The ``slug`` field is immutable.  Refreshes the registry cache after update.
    Raises 404 if the preset does not exist.
    """
    preset = await db.get(EmployeePreset, preset_id)
    if preset is None or preset.deleted_at is not None:
        raise NotFoundError(
            "employee_preset.not_found",
            "errors.employee_preset.not_found",
            f"EmployeePreset '{preset_id}' not found",
        )

    patch_data = body.model_dump(exclude_unset=True)
    for field, value in patch_data.items():
        setattr(preset, field, value)

    await db.commit()
    await db.refresh(preset)

    await registry.reload(db)
    return preset


@router.delete("/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_preset(
    preset_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> None:
    """Soft-delete a preset.

    The record is marked as deleted (``deleted_at`` is set) but not physically
    removed from the database.  Refreshes the registry cache after deletion.
    Raises 404 if the preset does not exist.
    """
    preset = await db.get(EmployeePreset, preset_id)
    if preset is None or preset.deleted_at is not None:
        raise NotFoundError(
            "employee_preset.not_found",
            "errors.employee_preset.not_found",
            f"EmployeePreset '{preset_id}' not found",
        )

    preset.soft_delete()
    await db.commit()

    await registry.reload(db)
