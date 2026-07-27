"""Learning API routes (P10 Wave 2).

Endpoints for the skill-distillation flow:

- GET  /learning/memories/{employee_id}/summary  — aggregated memory counts
- POST /learning/employees/{employee_id}/distill — distill memories into a new preset (201)
- GET  /learning/presets/{preset_id}             — fetch a distilled preset result
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUserDep
from app.core.distillation import AggregatingDistiller, DistillationError
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.event_types import LEARNING_DISTILLATION_COMPLETED
from app.core.events import emit
from app.core.openapi import add_error_responses
from app.core.permissions import require_office_role
from app.models.employee import Employee, EmployeePreset
from app.models.instance import Instance
from app.models.memory import MemoryEntry
from app.schemas.learning import (
    AggregatedMemoryCount,
    DistillRequest,
    DistillResultOut,
    MemorySummaryOut,
    SkillManifestPreview,
)

router = APIRouter(prefix="/learning", tags=["Learning"])
add_error_responses(router)


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
