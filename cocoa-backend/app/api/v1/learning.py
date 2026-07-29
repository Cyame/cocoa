"""Learning API routes (P10 Wave 2 + phase-15f capability lifecycle).

Endpoints for the skill-distillation and capability-lifecycle flows:

- GET  /learning/memories/{employee_id}/summary       — aggregated memory counts
- POST /learning/employees/{employee_id}/distill      — distill memories into a new preset (201)
- GET  /learning/presets/{preset_id}                  — fetch a distilled preset result
- POST /learning/instances/{iid}/reap                 — memory → capability (instance-private)
- POST /learning/entities/{eid}/promote               — instance cap → employee shared
- POST /learning/entities/{eid}/distill?action=transmute — employee → base class
- POST /learning/capabilities/combine                 — N capabilities → 1 gene
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUserDep
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
    compute_employee_migration_hash,
    compute_migration_hash,
)
from app.core.openapi import add_error_responses
from app.core.permissions import require_office_role
from app.models.ai_gene import AiGene
from app.models.base_class import BaseClass
from app.models.capability_market import (
    CapabilityCreatedVia,
    CapabilityMarketEntry,
    CapabilityType,
)
from app.models.employee import Employee, EmployeePreset
from app.models.instance import Instance
from app.models.memory import MemoryEntry
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


async def _get_office_id_for_employee(db: DB, employee_id: str) -> str:
    """Return the office_id for the first Instance of *employee_id*.

    Raises NotFoundError if the employee has no instance (and thus no office).
    """
    result = await db.execute(
        select(Instance.office_id).where(
            Instance.employee_id == employee_id,
            Instance.deleted_at.is_(None),
        ).limit(1)
    )
    office_id = result.scalar_one_or_none()
    if office_id is None:
        raise NotFoundError(
            "employee.no_office",
            "errors.employee.no_office",
            f"Employee {employee_id!r} is not associated with any office",
        )
    return office_id


# ---------------------------------------------------------------------------
# Memory summary
# ---------------------------------------------------------------------------


@router.get("/memories/{employee_id}/summary", response_model=MemorySummaryOut)
async def get_memory_summary(
    employee_id: str,
    db: DB,
    current_user: CurrentUserDep,
    kind: list[str] | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> MemorySummaryOut:
    """Return aggregated memory counts and sample data for an employee.

    Requires ``viewer`` role in the employee's office.
    Does **not** emit events (read-only).
    """
    # 1. Find Employee.
    emp = await db.get(Employee, employee_id)
    if emp is None or emp.deleted_at is not None:
        raise NotFoundError(
            "employee.not_found",
            "errors.employee.not_found",
            f"Employee {employee_id!r} not found",
        )

    # 2. Get office_id from employee's instance → check permission.
    office_id = await _get_office_id_for_employee(db, employee_id)
    await require_office_role(db, current_user.user_id, office_id, "viewer")

    # 3. Aggregate counts by kind (direct SQL).
    count_q = (
        select(MemoryEntry.kind, func.count(MemoryEntry.id))
        .where(
            MemoryEntry.employee_id == employee_id,
            MemoryEntry.deleted_at.is_(None),
        )
        .group_by(MemoryEntry.kind)
    )
    if kind is not None:
        count_q = count_q.where(MemoryEntry.kind.in_(kind))

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
        select(MemoryEntry.content)
        .where(
            MemoryEntry.employee_id == employee_id,
            MemoryEntry.kind == "lesson",
            MemoryEntry.content.isnot(None),
            MemoryEntry.deleted_at.is_(None),
        )
        .order_by(MemoryEntry.created_at.asc())
        .limit(min(limit, 5))
    )
    lesson_result = await db.execute(sample_lessons_q)
    sample_lessons: list[str] = [row[0] for row in lesson_result if row[0]]

    # 5. Sample keys by kind (up to 5 per kind).
    keys_q = (
        select(MemoryEntry.kind, MemoryEntry.key)
        .where(
            MemoryEntry.employee_id == employee_id,
            MemoryEntry.key.isnot(None),
            MemoryEntry.deleted_at.is_(None),
        )
    )
    if kind is not None:
        keys_q = keys_q.where(MemoryEntry.kind.in_(kind))

    keys_result = await db.execute(keys_q)
    sample_keys_by_kind: dict[str, list[str]] = {}
    for row in keys_result:
        k_kind, k_key = row[0], row[1]
        if k_kind not in sample_keys_by_kind:
            sample_keys_by_kind[k_kind] = []
        if k_key and len(sample_keys_by_kind[k_kind]) < 5:
            sample_keys_by_kind[k_kind].append(k_key)

    return MemorySummaryOut(
        employee_id=employee_id,
        aggregated_counts=aggregated,
        sample_lessons=sample_lessons,
        sample_keys_by_kind=sample_keys_by_kind,
    )


# ---------------------------------------------------------------------------
# Distill
# ---------------------------------------------------------------------------


@router.post(
    "/employees/{employee_id}/distill",
    response_model=DistillResultOut,
    status_code=status.HTTP_201_CREATED,
)
async def distill_employee(
    employee_id: str,
    body: DistillRequest,
    db: DB,
    current_user: CurrentUserDep,
) -> DistillResultOut:
    """Distill an employee's memory entries into a new EmployeePreset.

    Requires ``editor`` role in the employee's office.
    Emits ``LEARNING_DISTILLATION_COMPLETED`` inside the transaction.
    Returns 201 with the new preset identity and manifest preview.
    """
    # 1. Find Employee.
    emp = await db.get(Employee, employee_id)
    if emp is None or emp.deleted_at is not None:
        raise NotFoundError(
            "employee.not_found",
            "errors.employee.not_found",
            f"Employee {employee_id!r} not found",
        )

    # 2. Permission check — editor in the employee's office.
    office_id = await _get_office_id_for_employee(db, employee_id)
    await require_office_role(db, current_user.user_id, office_id, "editor")

    # 3. Run distillation.
    try:
        result = await AggregatingDistiller().distill(
            employee_id,
            request=body,
            session=db,
        )
    except DistillationError as exc:
        if exc.code == "employee.not_found":
            raise NotFoundError(exc.code, exc.message_key, exc.message) from exc
        raise ValidationError(exc.code, exc.message_key, exc.message) from exc

    # 4. Slug uniqueness check.
    slug = result.new_preset_slug
    existing = await db.execute(
        select(EmployeePreset).where(
            EmployeePreset.slug == slug,
            EmployeePreset.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(
            "employee_preset.slug_taken",
            "errors.employee_preset.slug_taken",
            f"EmployeePreset slug {slug!r} is already taken",
        )

    # 5. Create new preset inside transaction.
    preset_name = body.target_preset_name or f"Skill: {body.target_skill_slug}"
    manifest_dict = result.manifest_preview.model_dump()
    # Store source info in manifest for future reference.
    if result.source_preset_slug:
        manifest_dict["source_preset_slug"] = result.source_preset_slug

    new_preset = EmployeePreset(
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
        resource_type="employee_preset",
        resource_id=new_preset.id,
        payload={
            "employee_id": employee_id,
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
        source_employee_id=employee_id,
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
    Does **not** require office membership — any authenticated user can view.
    """
    preset = await db.get(EmployeePreset, preset_id)
    if preset is None or preset.deleted_at is not None:
        raise NotFoundError(
            "employee_preset.not_found",
            "errors.employee_preset.not_found",
            f"EmployeePreset {preset_id!r} not found",
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
        source_employee_id="",
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
) -> ReapResultOut:
    """Reap reusable capabilities from an instance's MemoryEntry log.

    Per PRD §13.6.3: distil memory entries into capability dicts, write
    them to the L1 capability_market (via ``created_via="reap"``) and to
    the instance's local runtime_config. The Employee row is NOT
    mutated (``entity_changed: false``).
    """
    instance = await db.get(Instance, instance_id)
    if instance is None or instance.deleted_at is not None:
        raise NotFoundError(
            "instance.not_found",
            "errors.instance.not_found",
            f"Instance {instance_id!r} not found",
        )

    employee = await db.get(Employee, instance.employee_id)
    if employee is None or employee.deleted_at is not None:
        raise NotFoundError(
            "employee.not_found",
            "errors.employee.not_found",
            f"Employee {instance.employee_id!r} not found",
        )

    await require_office_role(db, current_user.user_id, instance.office_id, "viewer")

    # 1. Pull memory entries visible to this instance.
    mem_q = (
        select(MemoryEntry)
        .where(
            MemoryEntry.deleted_at.is_(None),
            (MemoryEntry.source_instance_id == instance_id)
            | (MemoryEntry.employee_id == instance.employee_id),
        )
        .order_by(MemoryEntry.created_at.asc())
        .limit(body.max_capabilities)
    )
    if body.memory_kind_filter:
        mem_q = mem_q.where(MemoryEntry.kind.in_(body.memory_kind_filter))

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
            source_entity_slug=employee.slug,
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


@router.post("/entities/{employee_id}/promote", response_model=PromoteResultOut)
async def promote_employee(
    employee_id: str,
    body: PromoteRequest,
    db: DB,
    current_user: CurrentUserDep,
) -> PromoteResultOut:
    """Promote an instance's capability set into the Employee.

    Per PRD §13.6.4: idempotent union of instance caps into
    ``Employee.capabilities`` (matched by capability name), refresh of
    ``migration_hash``, and an event payload that lists how many
    other instances are now outdated (``active_hash != migration_hash``).
    """
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.deleted_at is not None:
        raise NotFoundError(
            "employee.not_found",
            "errors.employee.not_found",
            f"Employee {employee_id!r} not found",
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
        if instance.employee_id != employee_id:
            raise ValidationError(
                "instance.employee_mismatch",
                "errors.instance.employee_mismatch",
                "Instance does not belong to the given Employee",
            )
    else:
        result = await db.execute(
            select(Instance)
            .where(
                Instance.employee_id == employee_id,
                Instance.deleted_at.is_(None),
            )
            .order_by(Instance.created_at.asc())
            .limit(1)
        )
        instance = result.scalar_one_or_none()
        if instance is None:
            raise NotFoundError(
                "employee.no_instance",
                "errors.employee.no_instance",
                f"Employee {employee_id!r} has no active instance",
            )

    await require_office_role(db, current_user.user_id, instance.office_id, "editor")

    # 2. Compute instance's effective capability set.
    instance_runtime = instance.runtime_config or {}
    reaped_caps = list(instance_runtime.get("reaped_capabilities", []))
    if not reaped_caps:
        reaped_caps = list(employee.capabilities or [])

    # 3. Build idempotent union.
    existing_caps = list(employee.capabilities or [])
    existing_names = {c.get("name") for c in existing_caps if c.get("name")}
    promoted_now = 0
    merged = list(existing_caps)
    for cap in reaped_caps:
        name = cap.get("name")
        if not name or name in existing_names:
            continue
        merged.append(cap)
        existing_names.add(name)
        promoted_now += 1

    # 4. Decide prompt snapshot.
    prompt_regen = employee.prompt_regen_snapshot
    if body.include_prompt_regen:
        # v1: deterministic stub — hash of cap names + employee slug.
        seed = hashlib.sha256(
            (employee.slug + "|" + ",".join(sorted(existing_names))).encode("utf-8"),
        ).hexdigest()[:12]
        prompt_regen = (
            f"You are {employee.name}, an upgraded template (seed={seed}). "
            f"Capabilities: {', '.join(sorted(existing_names))}."
        )

    # 5. snapshot_only → preview without writing.
    if body.snapshot_only:
        return PromoteResultOut(
            promoted_at=datetime.now(timezone.utc).isoformat(),
            entity_id=employee_id,
            entity_promotion_migration_hash=compute_migration_hash(
                merged, prompt_regen,
            ),
            capability_promoted_count=promoted_now,
            prompt_regenerated=body.include_prompt_regen,
            new_prompt_preview=prompt_regen or "",
            outdated_instances_count=0,
            capability_market_uploaded=0,
        )

    # 6. Persist to Employee.
    employee.capabilities = merged
    employee.prompt_regen_snapshot = prompt_regen
    new_migration_hash = compute_employee_migration_hash(employee)
    employee.migration_hash = new_migration_hash

    # 7. Write promoted caps to capability_market (idempotent by name).
    market_uploaded = 0
    if promoted_now:
        new_names = [
            c["name"] for c in merged[-promoted_now:]
            if c.get("name")
        ]
        existing_market_names: set[str] = set()
        if new_names:
            market_q = await db.execute(
                select(CapabilityMarketEntry.name).where(
                    CapabilityMarketEntry.name.in_(new_names),
                    CapabilityMarketEntry.deleted_at.is_(None),
                )
            )
            existing_market_names = {row[0] for row in market_q}
        for cap in merged[-promoted_now:]:
            name = cap.get("name")
            if not name or name in existing_market_names:
                continue
            market_entry = CapabilityMarketEntry(
                name=name,
                type=cap.get("type", CapabilityType.skill.value),
                description=cap.get("description"),
                tags=cap.get("tags") or ["promoted"],
                created_via=CapabilityCreatedVia.promote.value,
                source_entity_slug=employee.slug,
            )
            db.add(market_entry)
            existing_market_names.add(name)
            market_uploaded += 1

    # 8. Count outdated instances (excluding the source instance).
    sibling_q = (
        select(Instance)
        .where(
            Instance.employee_id == employee_id,
            Instance.id != instance.id,
            Instance.deleted_at.is_(None),
        )
    )
    siblings = (await db.execute(sibling_q)).scalars().all()
    outdated_count = sum(
        1 for s in siblings if s.active_hash != new_migration_hash
    )

    # 9. Emit event.
    await emit(
        LEARNING_PROMOTE_COMPLETED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="employee",
        resource_id=employee.id,
        payload={
            "employee_id": employee_id,
            "new_migration_hash": new_migration_hash,
            "capability_promoted_count": promoted_now,
            "outdated_instances_count": outdated_count,
        },
        session=db,
    )

    await db.commit()

    return PromoteResultOut(
        promoted_at=datetime.now(timezone.utc).isoformat(),
        entity_id=employee_id,
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
    "/entities/{employee_id}/distill",
    response_model=TransmuteResultOut,
    status_code=status.HTTP_201_CREATED,
)
async def transmute_employee(
    employee_id: str,
    body: TransmuteRequest,
    action: str = Query("distill", description="Action type; 'transmute' for §13.6.5"),
    db: DB = None,
    current_user: CurrentUserDep = None,
) -> TransmuteResultOut:
    """Distill an Employee into a new BaseClass (L3 神职).

    Per PRD §13.6.5: pure derivative operation. The source Employee is
    NOT mutated and capability_market is NOT touched. Only the new
    BaseClass row is created.
    """
    if action != "transmute":
        raise ValidationError(
            "learning.action_unsupported",
            "errors.learning.action_unsupported",
            f"Action {action!r} is not supported on this endpoint; expected 'transmute'",
        )

    employee = await db.get(Employee, employee_id)
    if employee is None or employee.deleted_at is not None:
        raise NotFoundError(
            "employee.not_found",
            "errors.employee.not_found",
            f"Employee {employee_id!r} not found",
        )

    # Find an office for the employee to scope auth.
    inst_q = await db.execute(
        select(Instance.office_id).where(
            Instance.employee_id == employee_id,
            Instance.deleted_at.is_(None),
        ).limit(1)
    )
    office_id = inst_q.scalar_one_or_none()
    if office_id is None:
        raise NotFoundError(
            "employee.no_office",
            "errors.employee.no_office",
            f"Employee {employee_id!r} is not associated with any office",
        )

    await require_office_role(db, current_user.user_id, office_id, "editor")

    # 1. Build the new manifest.
    manifest = {
        "provider_config": {},
        "default_model": "tbd",
        "commands": [],
        "default_capabilities": list(employee.capabilities or []),
        "default_gene_refs": [],
        "system_prompt": employee.prompt_regen_snapshot or "",
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
            source_employee_id=employee_id,
        )

    # 4. Create BaseClass.
    new_bc = BaseClass(
        slug=body.target_base_class_slug,
        name=body.target_base_class_name,
        manifest=manifest,
        version="0.1.0",
    )
    db.add(new_bc)
    await db.flush()

    # 5. Emit event.
    await emit(
        LEARNING_DISTILL_TRANSMUTED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="base_class",
        resource_id=new_bc.id,
        payload={
            "source_employee_id": employee_id,
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
        source_employee_id=employee_id,
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
        kind=body.kind,
        tags=body.tags or [],
        manifest=manifest,
        gene_slugs=[],  # genome refs are an orthogonal concern
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
            "kind": body.kind,
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
