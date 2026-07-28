"""Office CRUD API routes.

Endpoints for managing collaboration workspaces.  All mutations create,
update, and soft-delete offices.  The ``slug`` field has a partial unique
index and is checked for conflicts on both create and update.

Routes (all require authentication):
    GET    /api/v1/offices       — List all active offices (offset page)
    GET    /api/v1/offices/{id}  — Get a single office
    POST   /api/v1/offices       — Create a new office (auto-adds creator as owner)
    PATCH  /api/v1/offices/{id}  — Update an existing office
    DELETE /api/v1/offices/{id}  — Soft-delete an office
"""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUserDep
from app.core.errors import ConflictError, NotFoundError
from app.core.openapi import add_error_responses
from app.core.pagination import OffsetPage, paginate_offset
from app.models.office import Membership, MembershipRole, Office
from app.schemas.office import OfficeCreate, OfficeOut, OfficeUpdate

router = APIRouter(prefix="/offices", tags=["Offices"])
add_error_responses(router)


@router.get("", response_model=OffsetPage[OfficeOut])
async def list_offices(
    db: DB,
    current_user: CurrentUserDep,
    limit: int = 50,
    offset: int = 0,
) -> OffsetPage:
    """Return a paginated list of active (non-deleted) offices."""
    stmt = (
        select(Office)
        .where(Office.deleted_at.is_(None))
        .order_by(Office.created_at)
    )
    return await paginate_offset(db, stmt, offset, min(limit, 200))


@router.get("/{office_id}", response_model=OfficeOut)
async def get_office(
    office_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> Office:
    """Return a single office by ID.

    Raises 404 if the office does not exist or has been soft-deleted.
    """
    office = await db.get(Office, office_id)
    if office is None or office.deleted_at is not None:
        raise NotFoundError(
            "office.not_found",
            "errors.office.not_found",
            f"Office '{office_id}' not found",
        )
    return office


@router.post("", response_model=OfficeOut, status_code=status.HTTP_201_CREATED)
async def create_office(
    body: OfficeCreate,
    db: DB,
    current_user: CurrentUserDep,
) -> Office:
    """Create a new office.

    The authenticated creator is automatically added as a :class:`Membership`
    with ``role='owner'`` so that the office is immediately usable by the
    creator (P14b-onboard2 onboarding fix).  Without this, the creator
    would hit "not a member of office" when fetching the office detail
    view.

    Raises 409 if an office with the same slug already exists (active).
    """
    existing = await db.execute(
        select(Office).where(
            Office.slug == body.slug,
            Office.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(
            "office.slug_taken",
            "errors.office.slug_taken",
            f"Office slug '{body.slug}' is already taken",
        )

    office = Office(
        name=body.name,
        slug=body.slug,
    )
    db.add(office)
    await db.flush()  # need office.id before creating the membership

    # P14b-onboard2: auto-create the creator as owner so the office is
    # immediately navigable. (0, 0) is fine because the owner is the first
    # membership in a fresh office.
    owner_membership = Membership(
        office_id=office.id,
        user_id=current_user.user_id,
        posx=0,
        posy=0,
        role=MembershipRole.owner.value,
    )
    db.add(owner_membership)

    await db.commit()
    await db.refresh(office)
    return office


@router.patch("/{office_id}", response_model=OfficeOut)
async def update_office(
    office_id: str,
    body: OfficeUpdate,
    db: DB,
    current_user: CurrentUserDep,
) -> Office:
    """Update an existing office.

    Only the fields provided in the request body are updated (partial update).
    The ``slug`` can be changed but is checked for uniqueness against other
    active offices.  Raises 404 if the office does not exist.
    """
    office = await db.get(Office, office_id)
    if office is None or office.deleted_at is not None:
        raise NotFoundError(
            "office.not_found",
            "errors.office.not_found",
            f"Office '{office_id}' not found",
        )

    patch_data = body.model_dump(exclude_unset=True)

    # Check slug uniqueness if slug is being changed (and differs from current)
    if "slug" in patch_data and patch_data["slug"] != office.slug:
        existing = await db.execute(
            select(Office).where(
                Office.slug == patch_data["slug"],
                Office.deleted_at.is_(None),
                Office.id != office_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ConflictError(
                "office.slug_taken",
                "errors.office.slug_taken",
                f"Office slug '{patch_data['slug']}' is already taken",
            )

    for field, value in patch_data.items():
        setattr(office, field, value)

    await db.commit()
    await db.refresh(office)
    return office


@router.delete("/{office_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_office(
    office_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> None:
    """Soft-delete an office.

    The record is marked as deleted (``deleted_at`` is set) but not physically
    removed from the database.  Raises 404 if the office does not exist.
    """
    office = await db.get(Office, office_id)
    if office is None or office.deleted_at is not None:
        raise NotFoundError(
            "office.not_found",
            "errors.office.not_found",
            f"Office '{office_id}' not found",
        )

    office.soft_delete()
    await db.commit()
