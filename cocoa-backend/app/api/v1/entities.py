"""Entity CRUD API routes.

Endpoints for managing agent cells (细胞).  All mutations (create, update,
delete) refresh the in-memory :class:`PresetRegistry` cache so that any
future preset-resolution logic sees the latest state.

Routes (all require authentication):
    GET    /api/v1/entities       — List all active entities (offset page)
    GET    /api/v1/entities/{id}  — Get a single entity
    POST   /api/v1/entities       — Create a new entity
    PATCH  /api/v1/entities/{id}  — Update an existing entity
    DELETE /api/v1/entities/{id}  — Soft-delete an entity
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DB, CurrentUserDep
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.openapi import add_error_responses
from app.core.pagination import OffsetPage, paginate_offset
from app.core.permissions import require_permission
from app.core.preset_registry import registry
from app.core.tenant import resolve_namespace_id
from app.models.ai_gene import AiGene
from app.models.capability_market import CapabilityMarketEntry
from app.models.entity import Entity
from app.schemas.entity import EntityCreate, EntityOut, EntityUpdate

router = APIRouter(prefix="/entities", tags=["Entitys"])
add_error_responses(router)


class EntityCapabilityAttachBody(BaseModel):
    capability_id: str


class EntityAiGeneAttachBody(BaseModel):
    ai_gene_id: str

# config_override keys that mirror capability/gene state — stripped on write
# (v4.0: the junction tables are the only write truth).
_CAP_OVERRIDE_KEYS = (
    "default_capabilities",
    "capabilities",
    "default_gene_refs",
    "gene_refs",
    "installed_genes",
)


def _strip_config_override_caps(override: dict | None) -> dict | None:
    if not isinstance(override, dict):
        return override
    return {k: v for k, v in override.items() if k not in _CAP_OVERRIDE_KEYS}


async def _entity_out(db: DB, entity: Entity) -> EntityOut:
    """Serialize an Entity with the capabilities mirror filled from junction."""
    from app.core.capabilities import load_entity_capability_dicts

    caps = await load_entity_capability_dicts(db, entity.id)
    return EntityOut(
        id=entity.id,
        namespace_id=entity.namespace_id,
        name=entity.name,
        slug=entity.slug,
        rank=entity.rank,
        preset_slug=entity.preset_slug,
        display_name=entity.display_name,
        display_color=entity.display_color,
        system_prompt=entity.system_prompt,
        config_override=entity.config_override,
        migration_hash=entity.migration_hash,
        capabilities=caps,
        is_cerebellum=entity.is_cerebellum,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


@router.get("", response_model=OffsetPage[EntityOut])
async def list_entities(
    db: DB,
    current_user: CurrentUserDep,
    limit: int = 50,
    offset: int = 0,
    namespace_id: str | None = Query(None),
) -> OffsetPage:
    """Return a paginated list of active (non-deleted) entities."""
    stmt = (
        select(Entity)
        .where(Entity.deleted_at.is_(None))
        .order_by(Entity.created_at)
    )
    if namespace_id is not None:
        stmt = stmt.where(Entity.namespace_id == namespace_id)
    page = await paginate_offset(db, stmt, offset, min(limit, 200))
    items = [await _entity_out(db, e) for e in page.items]
    return OffsetPage(
        items=items,
        offset=page.offset,
        limit=page.limit,
        total=page.total,
    )


@router.get("/{entity_id}", response_model=EntityOut)
async def get_entity(
    entity_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> EntityOut:
    """Return a single entity by ID.

    Raises 404 if the entity does not exist or has been soft-deleted.
    """
    entity = await db.get(Entity, entity_id)
    if entity is None or entity.deleted_at is not None:
        raise NotFoundError(
            "entity.not_found",
            "errors.entity.not_found",
            f"Entity '{entity_id}' not found",
        )
    return await _entity_out(db, entity)


@router.post("", response_model=EntityOut, status_code=status.HTTP_201_CREATED)
async def create_entity(
    body: EntityCreate,
    db: DB,
    current_user: CurrentUserDep,
) -> EntityOut:
    """Create a new entity.

    Raises 409 if an entity with the same slug already exists (active).
    Raises 422 if *preset_slug* is provided but does not exist in the
    preset registry.
    Refreshes the registry cache after creation.
    """
    namespace_id = await resolve_namespace_id(db, body.namespace_id)
    await require_permission(
        db, current_user.user_id, "can_manage_namespace", namespace_id=namespace_id
    )

    # Selection gate: validate preset_slug against registry.
    if body.preset_slug and not registry.get(body.preset_slug):
        raise ValidationError(
            "entity.preset_not_found",
            "errors.entity.preset_not_found",
            f"Preset '{body.preset_slug}' not found",
        )

    # Slug uniqueness check (partial unique index, so we check ourselves).
    existing = await db.execute(
        select(Entity).where(
            Entity.namespace_id == namespace_id,
            Entity.slug == body.slug,
            Entity.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(
            "entity.slug_taken",
            "errors.entity.slug_taken",
            f"Entity slug '{body.slug}' is already taken",
        )

    from app.core.migration_hash import compute_entity_migration_hash

    entity = Entity(
        namespace_id=namespace_id,
        name=body.name,
        slug=body.slug,
        rank=body.rank,
        preset_slug=body.preset_slug,
        display_name=body.display_name,
        display_color=body.display_color,
        system_prompt=body.system_prompt,
        config_override=_strip_config_override_caps(body.config_override),
    )
    db.add(entity)
    await db.flush()
    entity.migration_hash = await compute_entity_migration_hash(db, entity)
    await db.commit()
    await db.refresh(entity)

    await registry.reload(db)
    return await _entity_out(db, entity)


@router.patch("/{entity_id}", response_model=EntityOut)
async def update_entity(
    entity_id: str,
    body: EntityUpdate,
    db: DB,
    current_user: CurrentUserDep,
) -> EntityOut:
    """Update an existing entity.

    Only the fields provided in the request body are updated (partial update).
    The ``slug`` field is immutable.
    Raises 422 if *preset_slug* is provided but does not exist in the
    preset registry.
    Refreshes the registry cache after update.
    Raises 404 if the entity does not exist.
    """
    entity = await db.get(Entity, entity_id)
    if entity is None or entity.deleted_at is not None:
        raise NotFoundError(
            "entity.not_found",
            "errors.entity.not_found",
            f"Entity '{entity_id}' not found",
        )

    # Selection gate: validate preset_slug against registry.
    if body.preset_slug is not None and not registry.get(body.preset_slug):
        raise ValidationError(
            "entity.preset_not_found",
            "errors.entity.preset_not_found",
            f"Preset '{body.preset_slug}' not found",
        )

    patch_data = body.model_dump(exclude_unset=True)
    for field, value in patch_data.items():
        if field == "config_override":
            value = _strip_config_override_caps(value)
        setattr(entity, field, value)

    await db.commit()
    await db.refresh(entity)

    await registry.reload(db)
    return await _entity_out(db, entity)


@router.post("/{entity_id}/capabilities", status_code=status.HTTP_201_CREATED)
async def attach_entity_capability_route(
    entity_id: str,
    body: EntityCapabilityAttachBody,
    db: DB,
    current_user: CurrentUserDep,
) -> dict[str, str]:
    """Attach a capability to an entity."""
    from app.core.capabilities import attach_entity_capability

    entity = await db.get(Entity, entity_id)
    if entity is None or entity.deleted_at is not None:
        raise NotFoundError(
            "entity.not_found",
            "errors.entity.not_found",
            f"Entity '{entity_id}' not found",
        )
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_capabilities",
        namespace_id=entity.namespace_id,
    )
    cap = await db.get(CapabilityMarketEntry, body.capability_id)
    if cap is None or cap.deleted_at is not None:
        raise NotFoundError(
            "capability_market.not_found",
            "errors.capability_market.not_found",
            f"Capability '{body.capability_id}' not found",
        )
    await attach_entity_capability(
        db, entity_id=entity_id, capability_id=body.capability_id
    )
    await db.commit()
    return {"entity_id": entity_id, "capability_id": body.capability_id}


@router.delete(
    "/{entity_id}/capabilities/{capability_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def detach_entity_capability_route(
    entity_id: str,
    capability_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> None:
    """Detach a capability from an entity."""
    from app.core.capabilities import (
        bump_entity_migration_hash,
        detach_entity_capability,
    )

    entity = await db.get(Entity, entity_id)
    if entity is None or entity.deleted_at is not None:
        raise NotFoundError(
            "entity.not_found",
            "errors.entity.not_found",
            f"Entity '{entity_id}' not found",
        )
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_capabilities",
        namespace_id=entity.namespace_id,
    )
    await detach_entity_capability(
        db, entity_id=entity_id, capability_id=capability_id
    )
    await bump_entity_migration_hash(db, entity)
    await db.commit()


@router.post("/{entity_id}/ai-genes", status_code=status.HTTP_201_CREATED)
async def attach_entity_ai_gene_route(
    entity_id: str,
    body: EntityAiGeneAttachBody,
    db: DB,
    current_user: CurrentUserDep,
) -> dict[str, str]:
    """Attach an ai gene to an entity."""
    from app.core.capabilities import attach_entity_ai_gene

    entity = await db.get(Entity, entity_id)
    if entity is None or entity.deleted_at is not None:
        raise NotFoundError(
            "entity.not_found",
            "errors.entity.not_found",
            f"Entity '{entity_id}' not found",
        )
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_ai_genes",
        namespace_id=entity.namespace_id,
    )
    gene = await db.get(AiGene, body.ai_gene_id)
    if gene is None or gene.deleted_at is not None:
        raise NotFoundError(
            "ai_gene.not_found",
            "errors.ai_gene.not_found",
            f"AiGene '{body.ai_gene_id}' not found",
        )
    await attach_entity_ai_gene(db, entity_id=entity_id, ai_gene_id=body.ai_gene_id)
    await db.commit()
    return {"entity_id": entity_id, "ai_gene_id": body.ai_gene_id}


@router.delete(
    "/{entity_id}/ai-genes/{ai_gene_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def detach_entity_ai_gene_route(
    entity_id: str,
    ai_gene_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> None:
    """Detach an ai gene from an entity."""
    from app.core.capabilities import (
        bump_entity_migration_hash,
        detach_entity_ai_gene,
    )

    entity = await db.get(Entity, entity_id)
    if entity is None or entity.deleted_at is not None:
        raise NotFoundError(
            "entity.not_found",
            "errors.entity.not_found",
            f"Entity '{entity_id}' not found",
        )
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_ai_genes",
        namespace_id=entity.namespace_id,
    )
    await detach_entity_ai_gene(db, entity_id=entity_id, ai_gene_id=ai_gene_id)
    await bump_entity_migration_hash(db, entity)
    await db.commit()


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entity(
    entity_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> None:
    """Soft-delete a 眷族 (Entity).

    Refuses while any active 化身 (Instance) still exists for this entity —
    operators must exit / delete those Lost Ones first. Does **not** cascade
    wipe instances.
    """
    from app.models.instance import Instance

    entity = await db.get(Entity, entity_id)
    if entity is None or entity.deleted_at is not None:
        raise NotFoundError(
            "entity.not_found",
            "errors.entity.not_found",
            f"Entity '{entity_id}' not found",
        )

    active_instances = (
        await db.execute(
            select(Instance).where(
                Instance.entity_id == entity_id,
                Instance.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    if active_instances:
        ids = [inst.id for inst in active_instances]
        raise ConflictError(
            "entity.has_active_instances",
            "errors.entity.has_active_instances",
            (
                f"Cannot delete entity '{entity.slug}': "
                f"{len(ids)} active lost one(s) must be exited first"
            ),
            details={"instance_ids": ids, "count": len(ids)},
        )

    entity.soft_delete()
    await db.commit()

    await registry.reload(db)
