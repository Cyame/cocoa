"""Learning API routes (P10 Wave 2 + phase-15f capability lifecycle).

Endpoints for the skill-distillation and capability-lifecycle flows:

- GET  /learning/memories/{entity_id}/summary       — aggregated memory counts
- POST /learning/entities/{entity_id}/distill      — distill memories into a new preset (201)
- GET  /learning/presets/{preset_id}                  — fetch a distilled preset result
- POST /learning/instances/{iid}/reap                 — memory → capability (instance-private)
- POST /learning/entities/{eid}/promote               — instance cap → entity shared
- POST /learning/entities/{eid}/distill?action=transmute — entity → base class
- POST /learning/capabilities/combine                 — N capabilities → 1 gene
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUserDep, XOrgIdHeader
from app.core.distillation import AggregatingDistiller, DistillationError
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.event_types import (
    LEARNING_CAPABILITY_COMBINED,
    LEARNING_DISTILL_TRANSMUTED,
    LEARNING_DISTILLATION_COMPLETED,
    LEARNING_PROMOTE_COMPLETED,
    LEARNING_REAP_COMPLETED,
)
from app.core.events import emit
from app.core.migration_hash import (
    compute_entity_migration_hash,
    compute_migration_hash,
)
from app.core.openapi import add_error_responses
from app.core.pagination import OffsetPage, paginate_offset
from app.core.permissions import require_workspace_permission
from app.models.ai_gene import AiGene
from app.models.base_class import BaseClass
from app.models.capability_market import (
    CapabilityCreatedVia,
    CapabilityMarketEntry,
    CapabilityType,
)
from app.models.entity import Entity
from app.models.instance import Instance
from app.models.memory import Memory
from app.schemas.learning import (
    AggregatedMemoryCount,
    CombineRequest,
    CombineResultOut,
    DistillRequest,
    DistillResultOut,
    MemorySummaryOut,
    PromoteRequest,
    PromoteResultOut,
    ReapRequest,
    ReapResultOut,
    SkillManifestPreview,
    TransmuteRequest,
    TransmuteResultOut,
)

router = APIRouter(prefix="/learning", tags=["Learning"])
add_error_responses(router)

# Slugify a free-form string into a kebab-case token safe for use as a
# capability name. Strips non-alphanumerics, collapses runs of hyphens,
# and trims leading/trailing hyphens. Capped at 200 chars to fit the
# DB column (255 minus a buffer).
_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_REAP_DESC_CAP = 200


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_workspace_id_for_entity(db: DB, entity_id: str) -> str:
    """Return the workspace_id for the first Instance of *entity_id*.

    Raises NotFoundError if the entity has no instance (and thus no workspace).
    """
    result = await db.execute(
        select(Instance.workspace_id).where(
            Instance.entity_id == entity_id,
            Instance.deleted_at.is_(None),
        ).limit(1)
    )
    workspace_id = result.scalar_one_or_none()
    if workspace_id is None:
        raise NotFoundError(
            "entity.no_workspace",
            "errors.entity.no_workspace",
            f"Entity {entity_id!r} is not associated with any workspace",
        )
    return workspace_id


# ---------------------------------------------------------------------------
# Memory summary
# ---------------------------------------------------------------------------


@router.get("/memories/{entity_id}/summary", response_model=MemorySummaryOut)
async def get_memory_summary(
    entity_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
    kind: list[str] | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> MemorySummaryOut:
    """Return aggregated memory counts and sample data for an entity.

    Requires ``viewer`` role in the entity's workspace.
    Does **not** emit events (read-only).
    """
    # 1. Find Entity.
    emp = await db.get(Entity, entity_id)
    if emp is None or emp.deleted_at is not None:
        raise NotFoundError(
            "entity.not_found",
            "errors.entity.not_found",
            f"Entity {entity_id!r} not found",
        )

    # 2. Get workspace_id from entity's instance → check permission.
    workspace_id = await _get_workspace_id_for_entity(db, entity_id)
    await require_workspace_permission(
        db,
        current_user.user_id,
        workspace_id,
        "can_view_workspace",
        x_organization_id=x_organization_id,
    )

    # 3. Aggregate counts by kind (direct SQL).
    count_q = (
        select(Memory.kind, func.count(Memory.id))
        .where(
            Memory.entity_id == entity_id,
            Memory.deleted_at.is_(None),
        )
        .group_by(Memory.kind)
    )
    if kind is not None:
        count_q = count_q.where(Memory.kind.in_(kind))

    count_result = await db.execute(count_q)
    kind_counter: dict[str, int] = {
        "experience": 0,
        "lesson": 0,
        "decision": 0,
        "problem": 0,
    }
    for row in count_result:
        kind_counter[row[0]] = row[1]

    total = sum(kind_counter.values())
    aggregated = AggregatedMemoryCount(
        experience=kind_counter["experience"],
        lesson=kind_counter["lesson"],
        decision=kind_counter["decision"],
        problem=kind_counter["problem"],
        total=total,
    )

    # 4. Sample lessons (first <limit> lesson entries with non-empty content).
    #    Plan specifies first 5, but we use the query param for flexibility.
    sample_lessons_q = (
        select(Memory.content)
        .where(
            Memory.entity_id == entity_id,
            Memory.kind == "lesson",
            Memory.content.isnot(None),
            Memory.deleted_at.is_(None),
        )
        .order_by(Memory.created_at.asc())
        .limit(min(limit, 5))
    )
    lesson_result = await db.execute(sample_lessons_q)
    sample_lessons: list[str] = [row[0] for row in lesson_result if row[0]]

    # 5. Sample keys by kind (up to 5 per kind).
    keys_q = (
        select(Memory.kind, Memory.key)
        .where(
            Memory.entity_id == entity_id,
            Memory.key.isnot(None),
            Memory.deleted_at.is_(None),
        )
    )
    if kind is not None:
        keys_q = keys_q.where(Memory.kind.in_(kind))

    keys_result = await db.execute(keys_q)
    sample_keys_by_kind: dict[str, list[str]] = {}
    for row in keys_result:
        k_kind, k_key = row[0], row[1]
        if k_kind not in sample_keys_by_kind:
            sample_keys_by_kind[k_kind] = []
        if k_key and len(sample_keys_by_kind[k_kind]) < 5:
            sample_keys_by_kind[k_kind].append(k_key)

    return MemorySummaryOut(
        entity_id=entity_id,
        aggregated_counts=aggregated,
        sample_lessons=sample_lessons,
        sample_keys_by_kind=sample_keys_by_kind,
    )


# ---------------------------------------------------------------------------
# Distill
# ---------------------------------------------------------------------------


@router.post(
    "/entities/{entity_id}/distill",
    response_model=DistillResultOut,
    status_code=status.HTTP_201_CREATED,
)
async def distill_entity(
    entity_id: str,
    body: DistillRequest,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> DistillResultOut:
    """Distill an entity's memory entries into a new BaseClass.

    Requires ``editor`` role in the entity's workspace.
    Emits ``LEARNING_DISTILLATION_COMPLETED`` inside the transaction.
    Returns 201 with the new preset identity and manifest preview.
    """
    # 1. Find Entity.
    emp = await db.get(Entity, entity_id)
    if emp is None or emp.deleted_at is not None:
        raise NotFoundError(
            "entity.not_found",
            "errors.entity.not_found",
            f"Entity {entity_id!r} not found",
        )

    # 2. Permission check — editor in the entity's workspace.
    workspace_id = await _get_workspace_id_for_entity(db, entity_id)
    await require_workspace_permission(
        db,
        current_user.user_id,
        workspace_id,
        "can_edit_workspace",
        x_organization_id=x_organization_id,
    )

    # 3. Run distillation.
    try:
        result = await AggregatingDistiller().distill(
            entity_id,
            request=body,
            session=db,
        )
    except DistillationError as exc:
        if exc.code == "entity.not_found":
            raise NotFoundError(exc.code, exc.message_key, exc.message) from exc
        raise ValidationError(exc.code, exc.message_key, exc.message) from exc

    # 4. Slug uniqueness check.
    slug = result.new_preset_slug
    existing = await db.execute(
        select(BaseClass).where(
            BaseClass.slug == slug,
            BaseClass.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(
            "base_class.slug_taken",
            "errors.base_class.slug_taken",
            f"BaseClass slug {slug!r} is already taken",
        )

    # 5. Create new preset inside transaction.
    preset_name = body.target_preset_name or f"Skill: {body.target_skill_slug}"
    manifest_dict = result.manifest_preview.model_dump()
    # Store source info in manifest for future reference.
    if result.source_preset_slug:
        manifest_dict["source_preset_slug"] = result.source_preset_slug

    new_preset = BaseClass(
        slug=slug,
        name=preset_name,
        manifest=manifest_dict,
    )
    db.add(new_preset)
    await db.flush()

    # 6. Emit event within the same transaction.
    await emit(
        LEARNING_DISTILLATION_COMPLETED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="base_class",
        resource_id=new_preset.id,
        payload={
            "entity_id": entity_id,
            "new_preset_slug": slug,
            "source_preset_slug": result.source_preset_slug,
            "aggregated_counts": {
                "experience": result.aggregated_memory.experience,
                "lesson": result.aggregated_memory.lesson,
                "decision": result.aggregated_memory.decision,
                "problem": result.aggregated_memory.problem,
                "total": result.aggregated_memory.total,
            },
        },
        session=db,
    )

    # 7. Commit and refresh.
    await db.commit()
    await db.refresh(new_preset)

    return DistillResultOut(
        new_preset_id=new_preset.id,
        new_preset_slug=new_preset.slug,
        new_preset_name=new_preset.name,
        manifest_preview=result.manifest_preview,
        aggregated_memory=result.aggregated_memory,
        source_entity_id=entity_id,
        source_preset_slug=result.source_preset_slug,
    )


# ---------------------------------------------------------------------------
# Preset fetch (historical distill results)
# ---------------------------------------------------------------------------


@router.get("/presets/{preset_id}", response_model=DistillResultOut)
async def get_learning_preset(
    preset_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> DistillResultOut:
    """Fetch a previously distilled preset by its UUID.

    Returns the distill result with manifest preview.
    Does **not** require workspace membership — any authenticated user can view.
    """
    preset = await db.get(BaseClass, preset_id)
    if preset is None or preset.deleted_at is not None:
        raise NotFoundError(
            "base_class.not_found",
            "errors.base_class.not_found",
            f"BaseClass {preset_id!r} not found",
        )

    manifest_data = preset.manifest if isinstance(preset.manifest, dict) else {}
    manifest_preview = SkillManifestPreview.model_validate(manifest_data)

    source_preset_slug: str | None = None
    if isinstance(preset.manifest, dict):
        source_preset_slug = preset.manifest.get("source_preset_slug")

    return DistillResultOut(
        new_preset_id=preset.id,
        new_preset_slug=preset.slug,
        new_preset_name=preset.name,
        manifest_preview=manifest_preview,
        aggregated_memory=AggregatedMemoryCount(),
        source_entity_id="",
        source_preset_slug=source_preset_slug,
    )


# ---------------------------------------------------------------------------
# Phase-15f capability lifecycle (PRD §13.6.3–§13.6.5)
# ---------------------------------------------------------------------------


def _slugify_capability_name(text: str) -> str:
    """Convert *text* into a kebab-case capability slug.

    Lower-cases, replaces runs of non-alphanumerics with single hyphens,
    and trims leading/trailing hyphens. Falls back to ``"capability"`` if
    the input contains no alphanumerics.
    """
    lowered = text.lower().strip()
    slug = _SLUG_NON_ALNUM.sub("-", lowered).strip("-")
    if not slug:
        return "capability"
    return slug[:200]


def _truncate_for_description(text: str, max_chars: int = _REAP_DESC_CAP) -> str:
    """Truncate *text* to *max_chars*, appending ``"..."`` if truncated."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


# ---------------------------------------------------------------------------
# Endpoint A: POST /learning/instances/{iid}/reap
# ---------------------------------------------------------------------------


@router.post("/instances/{instance_id}/reap", response_model=ReapResultOut)
async def reap_instance(
    instance_id: str,
    body: ReapRequest,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> ReapResultOut:
    """Reap reusable capabilities from an instance's Memory log.

    Per PRD §13.6.3: distil memory entries into capability dicts, write
    them to the L1 capability_market (via ``created_via="reap"``) and to
    the instance's local runtime_config. The Entity row is NOT
    mutated (``entity_changed: false``).
    """
    instance = await db.get(Instance, instance_id)
    if instance is None or instance.deleted_at is not None:
        raise NotFoundError(
            "instance.not_found",
            "errors.instance.not_found",
            f"Instance {instance_id!r} not found",
        )

    entity = await db.get(Entity, instance.entity_id)
    if entity is None or entity.deleted_at is not None:
        raise NotFoundError(
            "entity.not_found",
            "errors.entity.not_found",
            f"Entity {instance.entity_id!r} not found",
        )

    await require_workspace_permission(
        db,
        current_user.user_id,
        instance.workspace_id,
        "can_view_workspace",
        x_organization_id=x_organization_id,
    )

    # 1. Pull memory entries visible to this instance.
    mem_q = (
        select(Memory)
        .where(
            Memory.deleted_at.is_(None),
            (Memory.source_instance_id == instance_id)
            | (Memory.entity_id == instance.entity_id),
        )
        .order_by(Memory.created_at.asc())
        .limit(body.max_capabilities)
    )
    if body.memory_kind_filter:
        mem_q = mem_q.where(Memory.kind.in_(body.memory_kind_filter))

    mem_rows = (await db.execute(mem_q)).scalars().all()
    memory_consumed = len(mem_rows)

    # 2. Distil — deterministic, no LLM. Each memory → one capability.
    distilled: list[dict] = []
    for entry in mem_rows:
        seed_text = entry.key or entry.content or entry.kind
        cap_name = _slugify_capability_name(seed_text)
        description = _truncate_for_description(entry.content or entry.key or entry.kind)
        distilled.append({
            "name": cap_name,
            "type": CapabilityType.skill.value,
            "description": description,
            "tags": ["auto-distilled"],
            "source_kind": entry.kind,
            "source_memory_id": entry.id,
        })

    # 3. snapshot_only → return preview without writing.
    if body.snapshot_only:
        return ReapResultOut(
            reaped_at=datetime.now(timezone.utc).isoformat(),
            instance_id=instance_id,
            memory_consumed=memory_consumed,
            capability_distilled=distilled,
            capability_market_uploaded=0,
            instance_local_added=0,
            entity_changed=False,
        )

    # 4. Write to capability_market (idempotent by name).
    market_uploaded = 0
    existing_names: set[str] = set()
    if distilled:
        market_q = await db.execute(
            select(CapabilityMarketEntry.name).where(
                CapabilityMarketEntry.name.in_([c["name"] for c in distilled]),
                CapabilityMarketEntry.deleted_at.is_(None),
            )
        )
        existing_names = {row[0] for row in market_q}

    for cap in distilled:
        if cap["name"] in existing_names:
            continue
        market_entry = CapabilityMarketEntry(
            name=cap["name"],
            type=cap["type"],
            description=cap["description"],
            tags=cap["tags"],
            created_via=CapabilityCreatedVia.reap.value,
            source_entity_slug=entity.slug,
        )
        db.add(market_entry)
        existing_names.add(cap["name"])
        market_uploaded += 1

    # 5. Write to instance runtime_config["reaped_capabilities"] (append).
    runtime_config = dict(instance.runtime_config or {})
    existing_reaped = list(runtime_config.get("reaped_capabilities", []))
    for cap in distilled:
        if cap["name"] not in {c.get("name") for c in existing_reaped}:
            existing_reaped.append(cap)
    runtime_config["reaped_capabilities"] = existing_reaped
    instance.runtime_config = runtime_config

    # 6. Emit event within transaction.
    await emit(
        LEARNING_REAP_COMPLETED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="instance",
        resource_id=instance.id,
        payload={
            "instance_id": instance_id,
            "memory_consumed": memory_consumed,
            "capabilities_count": len(distilled),
            "capability_market_uploaded": market_uploaded,
        },
        session=db,
    )

    await db.commit()

    return ReapResultOut(
        reaped_at=datetime.now(timezone.utc).isoformat(),
        instance_id=instance_id,
        memory_consumed=memory_consumed,
        capability_distilled=distilled,
        capability_market_uploaded=market_uploaded,
        instance_local_added=len(distilled),
        entity_changed=False,
    )


# ---------------------------------------------------------------------------
# Endpoint B: POST /learning/entities/{eid}/promote
# ---------------------------------------------------------------------------


@router.post("/entities/{entity_id}/promote", response_model=PromoteResultOut)
async def promote_entity(
    entity_id: str,
    body: PromoteRequest,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> PromoteResultOut:
    """Promote an instance's capability set into the Entity (回魂) or fork a new Entity (派生)."""
    entity = await db.get(Entity, entity_id)
    if entity is None or entity.deleted_at is not None:
        raise NotFoundError(
            "entity.not_found",
            "errors.entity.not_found",
            f"Entity {entity_id!r} not found",
        )

    if body.mode == "fork":
        if not body.new_entity_name or not body.new_entity_slug:
            raise ValidationError(
                "promote.fork_fields_required",
                "errors.promote.fork_fields_required",
                "new_entity_name and new_entity_slug are required when mode=fork",
            )
        slug_clash = await db.execute(
            select(Entity).where(
                Entity.namespace_id == entity.namespace_id,
                Entity.slug == body.new_entity_slug,
                Entity.deleted_at.is_(None),
            )
        )
        if slug_clash.scalar_one_or_none() is not None:
            raise ConflictError(
                "entity.slug_taken",
                "errors.entity.slug_taken",
                f"Entity slug '{body.new_entity_slug}' already taken in namespace",
            )

    # 1. Resolve source instance.
    if body.from_instance_id:
        instance = await db.get(Instance, body.from_instance_id)
        if instance is None or instance.deleted_at is not None:
            raise NotFoundError(
                "instance.not_found",
                "errors.instance.not_found",
                f"Instance {body.from_instance_id!r} not found",
            )
        if instance.entity_id != entity_id:
            raise ValidationError(
                "instance.entity_mismatch",
                "errors.instance.entity_mismatch",
                "Instance does not belong to the given Entity",
            )
    else:
        result = await db.execute(
            select(Instance)
            .where(
                Instance.entity_id == entity_id,
                Instance.deleted_at.is_(None),
            )
            .order_by(Instance.created_at.asc())
            .limit(1)
        )
        instance = result.scalar_one_or_none()
        if instance is None:
            raise NotFoundError(
                "entity.no_instance",
                "errors.entity.no_instance",
                f"Entity {entity_id!r} has no active instance",
            )

    await require_workspace_permission(
        db,
        current_user.user_id,
        instance.workspace_id,
        "can_edit_workspace",
        x_organization_id=x_organization_id,
    )

    # 2. Compute instance's effective capability set (v4.0: junction is truth).
    from app.core.capabilities import (
        attach_entity_capability,
        load_entity_capability_dicts,
        upsert_capability,
    )

    existing_caps = await load_entity_capability_dicts(db, entity.id)
    instance_runtime = instance.runtime_config or {}
    reaped_caps = list(instance_runtime.get("reaped_capabilities", []))
    if not reaped_caps:
        reaped_caps = list(existing_caps)

    # 3. Build idempotent union.
    existing_names = {c.get("name") for c in existing_caps if c.get("name")}
    promoted_now = 0
    merged = list(existing_caps)
    new_caps: list[dict] = []
    for cap in reaped_caps:
        name = cap.get("name") if isinstance(cap, dict) else None
        if not name or name in existing_names:
            continue
        merged.append(cap)
        new_caps.append(cap)
        existing_names.add(name)
        promoted_now += 1

    # 4. Decide prompt snapshot (prefer Entity.system_prompt overlay).
    prompt_regen = entity.system_prompt
    if body.include_prompt_regen:
        seed = hashlib.sha256(
            (entity.slug + "|" + ",".join(sorted(existing_names))).encode("utf-8"),
        ).hexdigest()[:12]
        prompt_regen = (
            f"You are {entity.name}, an upgraded template (seed={seed}). "
            f"Capabilities: {', '.join(sorted(existing_names))}."
        )

    # 5. snapshot_only → preview without writing.
    if body.snapshot_only:
        return PromoteResultOut(
            mode=body.mode,
            promoted_at=datetime.now(timezone.utc).isoformat(),
            entity_id=entity_id,
            entity_promotion_migration_hash=compute_migration_hash(
                merged, prompt_regen,
            ),
            capability_promoted_count=promoted_now,
            prompt_regenerated=body.include_prompt_regen,
            new_prompt_preview=prompt_regen or "",
            outdated_instances_count=0,
            capability_market_uploaded=0,
        )

    if body.mode == "fork":
        new_entity = Entity(
            namespace_id=entity.namespace_id,
            name=body.new_entity_name,
            slug=body.new_entity_slug,
            preset_slug=entity.preset_slug,
            rank=entity.rank,
            display_name=body.new_entity_name,
            display_color=entity.display_color,
            system_prompt=prompt_regen if body.include_prompt_regen else entity.system_prompt,
            config_override=entity.config_override,
        )
        db.add(new_entity)
        await db.flush()
        # v4.0 §6.4: fork copies the merged capability set via junction rows.
        from app.models.organization import Namespace

        ns = await db.get(Namespace, entity.namespace_id)
        fork_org_id = ns.org_id if ns is not None else None
        for cap in merged:
            name = cap.get("name") if isinstance(cap, dict) else None
            if not name:
                continue
            market = await upsert_capability(
                db,
                name=name,
                cap_type=cap.get("type") or "skill",
                scope="org" if fork_org_id else "system",
                organization_id=fork_org_id,
                created_via="promote",
                description=cap.get("description"),
                config_template=cap.get("config_template") or cap.get("config"),
                source_entity_slug=entity.slug,
            )
            await attach_entity_capability(
                db, entity_id=new_entity.id, capability_id=market.id
            )
        new_migration_hash = await compute_entity_migration_hash(db, new_entity)
        new_entity.migration_hash = new_migration_hash

        await emit(
            LEARNING_PROMOTE_COMPLETED,
            actor_type="user",
            actor_id=current_user.user_id,
            resource_type="entity",
            resource_id=new_entity.id,
            payload={
                "mode": "fork",
                "source_entity_id": entity_id,
                "entity_id": new_entity.id,
                "new_migration_hash": new_migration_hash,
                "capability_promoted_count": promoted_now,
            },
            session=db,
        )
        await db.commit()
        return PromoteResultOut(
            mode="fork",
            promoted_at=datetime.now(timezone.utc).isoformat(),
            entity_id=entity_id,
            new_entity_id=new_entity.id,
            entity_promotion_migration_hash=new_migration_hash,
            capability_promoted_count=promoted_now,
            prompt_regenerated=body.include_prompt_regen,
            new_prompt_preview=prompt_regen or "",
            outdated_instances_count=0,
            capability_market_uploaded=0,
        )

    # 6. Persist via junction (v4.0 §6.4 — JSONB write path removed).
    from app.models.organization import Namespace

    ns = await db.get(Namespace, entity.namespace_id)
    entity_org_id = ns.org_id if ns is not None else None
    for cap in new_caps:
        market = await upsert_capability(
            db,
            name=cap["name"],
            cap_type=cap.get("type") or "skill",
            scope="org" if entity_org_id else "system",
            organization_id=entity_org_id,
            created_via="promote",
            description=cap.get("description"),
            config_template=cap.get("config_template") or cap.get("config"),
            source_entity_slug=entity.slug,
        )
        await attach_entity_capability(
            db, entity_id=entity.id, capability_id=market.id
        )
    if body.include_prompt_regen and prompt_regen:
        entity.system_prompt = prompt_regen
    new_migration_hash = await compute_entity_migration_hash(db, entity)
    entity.migration_hash = new_migration_hash

    market_uploaded = 0

    # 7. Count outdated instances (excluding the source instance).
    sibling_q = (
        select(Instance)
        .where(
            Instance.entity_id == entity_id,
            Instance.id != instance.id,
            Instance.deleted_at.is_(None),
        )
    )
    siblings = (await db.execute(sibling_q)).scalars().all()
    outdated_count = sum(
        1 for s in siblings if s.active_hash != new_migration_hash
    )

    # 8. Emit event.
    await emit(
        LEARNING_PROMOTE_COMPLETED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="entity",
        resource_id=entity.id,
        payload={
            "mode": "update",
            "entity_id": entity_id,
            "new_migration_hash": new_migration_hash,
            "capability_promoted_count": promoted_now,
            "outdated_instances_count": outdated_count,
        },
        session=db,
    )

    await db.commit()

    return PromoteResultOut(
        mode="update",
        promoted_at=datetime.now(timezone.utc).isoformat(),
        entity_id=entity_id,
        entity_promotion_migration_hash=new_migration_hash,
        capability_promoted_count=promoted_now,
        prompt_regenerated=body.include_prompt_regen,
        new_prompt_preview=prompt_regen or "",
        outdated_instances_count=outdated_count,
        capability_market_uploaded=market_uploaded,
    )


# ---------------------------------------------------------------------------
# Endpoint C: POST /learning/entities/{eid}/distill?action=transmute
# ---------------------------------------------------------------------------


@router.post(
    "/entities/{entity_id}/transmute",
    response_model=TransmuteResultOut,
    status_code=status.HTTP_201_CREATED,
)
async def transmute_entity(
    entity_id: str,
    body: TransmuteRequest,
    db: DB = None,
    current_user: CurrentUserDep = None,
    x_organization_id: XOrgIdHeader = None,
) -> TransmuteResultOut:
    """Distill an Entity into a new BaseClass (L3 神职).

    Per PRD §13.6.5: pure derivative operation. The source Entity is
    NOT mutated and capability_market is NOT touched. Only the new
    BaseClass row is created.
    """
    entity = await db.get(Entity, entity_id)
    if entity is None or entity.deleted_at is not None:
        raise NotFoundError(
            "entity.not_found",
            "errors.entity.not_found",
            f"Entity {entity_id!r} not found",
        )

    # Find an workspace for the entity to scope auth.
    inst_q = await db.execute(
        select(Instance.workspace_id).where(
            Instance.entity_id == entity_id,
            Instance.deleted_at.is_(None),
        ).limit(1)
    )
    workspace_id = inst_q.scalar_one_or_none()
    if workspace_id is None:
        raise NotFoundError(
            "entity.no_workspace",
            "errors.entity.no_workspace",
            f"Entity {entity_id!r} is not associated with any workspace",
        )

    await require_workspace_permission(
        db,
        current_user.user_id,
        workspace_id,
        "can_edit_workspace",
        x_organization_id=x_organization_id,
    )

    # 1. Build the new manifest (v4.0: capability truth is the junction).
    from app.core.capabilities import (
        attach_base_class_capability,
        load_entity_capability_dicts,
        upsert_capability,
    )
    from app.models.organization import Namespace

    entity_caps = await load_entity_capability_dicts(db, entity.id)
    ns = await db.get(Namespace, entity.namespace_id)
    entity_org_id = ns.org_id if ns is not None else None
    manifest = {
        "provider_config": {},
        "default_model": "tbd",
        "commands": [],
        "default_capabilities": list(entity_caps),
        "default_gene_refs": [],
        "system_prompt": entity.system_prompt or "",
    }

    # 2. Slug uniqueness check.
    existing_q = await db.execute(
        select(BaseClass).where(
            BaseClass.slug == body.target_base_class_slug,
            BaseClass.deleted_at.is_(None),
        )
    )
    if existing_q.scalar_one_or_none() is not None:
        raise ConflictError(
            "base_class.slug_taken",
            "errors.base_class.slug_taken",
            f"BaseClass slug {body.target_base_class_slug!r} is already taken",
        )

    # 3. snapshot_only → preview without writing.
    if body.snapshot_only:
        return TransmuteResultOut(
            new_base_class_id="",
            new_base_class_slug=body.target_base_class_slug,
            new_base_class_name=body.target_base_class_name,
            manifest_preview=manifest,
            source_entity_id=entity_id,
        )

    # 4. Create BaseClass (org scope) + base_class_capabilities junction (§6.4).
    new_bc = BaseClass(
        slug=body.target_base_class_slug,
        name=body.target_base_class_name,
        manifest=manifest,
        scope="org" if entity_org_id else "system",
        organization_id=entity_org_id,
        version="0.1.0",
    )
    db.add(new_bc)
    await db.flush()
    for cap in entity_caps:
        name = cap.get("name")
        if not name:
            continue
        market = await upsert_capability(
            db,
            name=name,
            cap_type=cap.get("type") or "skill",
            scope="org" if entity_org_id else "system",
            organization_id=entity_org_id,
            created_via="manual",
            description=cap.get("description"),
            config_template=cap.get("config_template") or cap.get("config"),
        )
        await attach_base_class_capability(
            db, base_class_id=new_bc.id, capability_id=market.id
        )

    # 5. Emit event.
    await emit(
        LEARNING_DISTILL_TRANSMUTED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="base_class",
        resource_id=new_bc.id,
        payload={
            "source_entity_id": entity_id,
            "new_base_class_slug": new_bc.slug,
            "capability_count": len(manifest["default_capabilities"]),
        },
        session=db,
    )

    await db.commit()
    await db.refresh(new_bc)

    return TransmuteResultOut(
        new_base_class_id=new_bc.id,
        new_base_class_slug=new_bc.slug,
        new_base_class_name=new_bc.name,
        manifest_preview=manifest,
        source_entity_id=entity_id,
    )


# ---------------------------------------------------------------------------
# Endpoint D: POST /learning/capabilities/combine
# ---------------------------------------------------------------------------


@router.post(
    "/capabilities/combine",
    response_model=CombineResultOut,
    status_code=status.HTTP_201_CREATED,
)
async def combine_capabilities(
    body: CombineRequest,
    db: DB,
    current_user: CurrentUserDep,
) -> CombineResultOut:
    """Package N L1 capabilities into a single L2 Gene (AiGene).

    Per PRD §13.6.10.2.2: all referenced capability names must exist in
    the capability_market (otherwise 404). The new gene references them
    by name in its manifest.
    """
    # 1. Validate all referenced capabilities exist.
    cap_q = await db.execute(
        select(CapabilityMarketEntry).where(
            CapabilityMarketEntry.name.in_(body.capability_names),
            CapabilityMarketEntry.deleted_at.is_(None),
        )
    )
    found = {c.name: c for c in cap_q.scalars().all()}
    missing = [n for n in body.capability_names if n not in found]
    if missing:
        raise NotFoundError(
            "capability.not_found",
            "errors.capability.not_found",
            f"Capability(s) not found: {missing}",
            details={"missing": missing},
        )

    # 2. Build manifest preview.
    manifest = {
        "capabilities": [
            {
                "name": found[n].name,
                "type": found[n].type,
                "description": found[n].description,
            }
            for n in body.capability_names
        ],
        "tools": [],
        "scripts": {},
        "runtime_config": {},
    }

    # 3. Slug uniqueness check.
    existing_gene = await db.execute(
        select(AiGene).where(
            AiGene.slug == body.gene_slug,
            AiGene.deleted_at.is_(None),
        )
    )
    if existing_gene.scalar_one_or_none() is not None:
        raise ConflictError(
            "ai_gene.slug_taken",
            "errors.ai_gene.slug_taken",
            f"AiGene slug {body.gene_slug!r} is already taken",
        )

    # 4. snapshot_only → preview without writing.
    if body.snapshot_only:
        return CombineResultOut(
            new_gene_id="",
            new_gene_slug=body.gene_slug,
            referenced_capabilities=list(body.capability_names),
            manifest_preview=manifest,
        )

    # 5. Create AiGene.
    new_gene = AiGene(
        slug=body.gene_slug,
        name=body.gene_name,
        tags=body.tags or [],
        manifest=manifest,
    )
    db.add(new_gene)
    await db.flush()

    # 6. Emit event.
    await emit(
        LEARNING_CAPABILITY_COMBINED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="ai_gene",
        resource_id=new_gene.id,
        payload={
            "gene_slug": body.gene_slug,
            "referenced_capabilities": list(body.capability_names),
        },
        session=db,
    )

    await db.commit()
    await db.refresh(new_gene)

    return CombineResultOut(
        new_gene_id=new_gene.id,
        new_gene_slug=new_gene.slug,
        referenced_capabilities=list(body.capability_names),
        manifest_preview=manifest,
    )
