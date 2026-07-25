"""Employee CRUD API routes.

Endpoints for managing agent cells (细胞).  All mutations (create, update,
delete) refresh the in-memory :class:`PresetRegistry` cache so that any
future preset-resolution logic sees the latest state.

Routes (all require authentication):
    GET    /api/v1/employees       — List all active employees (offset page)
    GET    /api/v1/employees/{id}  — Get a single employee
    POST   /api/v1/employees       — Create a new employee
    PATCH  /api/v1/employees/{id}  — Update an existing employee
    DELETE /api/v1/employees/{id}  — Soft-delete an employee
"""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUserDep
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.openapi import add_error_responses
from app.core.pagination import OffsetPage, paginate_offset
from app.core.preset_registry import registry
from app.models.employee import Employee
from app.schemas.employee import EmployeeCreate, EmployeeOut, EmployeeUpdate

router = APIRouter(prefix="/employees", tags=["Employees"])
add_error_responses(router)


@router.get("", response_model=OffsetPage[EmployeeOut])
async def list_employees(
    db: DB,
    current_user: CurrentUserDep,
    limit: int = 50,
    offset: int = 0,
) -> OffsetPage:
    """Return a paginated list of active (non-deleted) employees."""
    stmt = (
        select(Employee)
        .where(Employee.deleted_at.is_(None))
        .order_by(Employee.created_at)
    )
    return await paginate_offset(db, stmt, offset, min(limit, 200))


@router.get("/{employee_id}", response_model=EmployeeOut)
async def get_employee(
    employee_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> Employee:
    """Return a single employee by ID.

    Raises 404 if the employee does not exist or has been soft-deleted.
    """
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.deleted_at is not None:
        raise NotFoundError(
            "employee.not_found",
            "errors.employee.not_found",
            f"Employee '{employee_id}' not found",
        )
    return employee


@router.post("", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
async def create_employee(
    body: EmployeeCreate,
    db: DB,
    current_user: CurrentUserDep,
) -> Employee:
    """Create a new employee.

    Raises 409 if an employee with the same slug already exists (active).
    Raises 422 if *preset_slug* is provided but does not exist in the
    preset registry.
    Refreshes the registry cache after creation.
    """
    # Selection gate: validate preset_slug against registry.
    if body.preset_slug and not registry.get(body.preset_slug):
        raise ValidationError(
            "employee.preset_not_found",
            "errors.employee.preset_not_found",
            f"Preset '{body.preset_slug}' not found",
        )

    # Slug uniqueness check (partial unique index, so we check ourselves).
    existing = await db.execute(
        select(Employee).where(
            Employee.slug == body.slug,
            Employee.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(
            "employee.slug_taken",
            "errors.employee.slug_taken",
            f"Employee slug '{body.slug}' is already taken",
        )

    employee = Employee(
        name=body.name,
        slug=body.slug,
        rank=body.rank,
        preset_slug=body.preset_slug,
        display_name=body.display_name,
        display_color=body.display_color,
    )
    db.add(employee)
    await db.commit()
    await db.refresh(employee)

    await registry.reload(db)
    return employee


@router.patch("/{employee_id}", response_model=EmployeeOut)
async def update_employee(
    employee_id: str,
    body: EmployeeUpdate,
    db: DB,
    current_user: CurrentUserDep,
) -> Employee:
    """Update an existing employee.

    Only the fields provided in the request body are updated (partial update).
    The ``slug`` field is immutable.
    Raises 422 if *preset_slug* is provided but does not exist in the
    preset registry.
    Refreshes the registry cache after update.
    Raises 404 if the employee does not exist.
    """
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.deleted_at is not None:
        raise NotFoundError(
            "employee.not_found",
            "errors.employee.not_found",
            f"Employee '{employee_id}' not found",
        )

    # Selection gate: validate preset_slug against registry.
    if body.preset_slug is not None and not registry.get(body.preset_slug):
        raise ValidationError(
            "employee.preset_not_found",
            "errors.employee.preset_not_found",
            f"Preset '{body.preset_slug}' not found",
        )

    patch_data = body.model_dump(exclude_unset=True)
    for field, value in patch_data.items():
        setattr(employee, field, value)

    await db.commit()
    await db.refresh(employee)

    await registry.reload(db)
    return employee


@router.delete("/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_employee(
    employee_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> None:
    """Soft-delete an employee.

    The record is marked as deleted (``deleted_at`` is set) but not physically
    removed from the database.  Refreshes the registry cache after deletion.
    Raises 404 if the employee does not exist.
    """
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.deleted_at is not None:
        raise NotFoundError(
            "employee.not_found",
            "errors.employee.not_found",
            f"Employee '{employee_id}' not found",
        )

    employee.soft_delete()
    await db.commit()

    await registry.reload(db)
