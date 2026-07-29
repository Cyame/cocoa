"""Organization API — default tenant (PRD-v2).

Routes:
    GET   /api/v1/organizations/default  — read default org
    PATCH /api/v1/organizations/default  — update default org (super-admin)
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DB, CurrentUserDep
from app.core.errors import NotFoundError
from app.core.openapi import add_error_responses
from app.core.permissions import require_super_admin
from app.models.organization import Organization
from app.schemas.organization import OrganizationOut, OrganizationUpdate

router = APIRouter(prefix="/organizations", tags=["Organizations"])
add_error_responses(router)


async def _get_default_org(db: DB) -> Organization:
    result = await db.execute(
        select(Organization).where(
            Organization.slug == "default",
            Organization.deleted_at.is_(None),
        )
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise NotFoundError(
            "organization.not_found",
            "errors.organization.not_found",
            "Default organization not found — run alembic upgrade head",
        )
    return org


@router.get("/default", response_model=OrganizationOut)
async def get_default_organization(
    db: DB,
    current_user: CurrentUserDep,
) -> Organization:
    """Return the seeded ``default`` Organization."""
    return await _get_default_org(db)


@router.patch("/default", response_model=OrganizationOut)
async def update_default_organization(
    body: OrganizationUpdate,
    db: DB,
    current_user: CurrentUserDep,
) -> Organization:
    """Partial-update the default Organization (super-admin only)."""
    require_super_admin(current_user)
    org = await _get_default_org(db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(org, field, value)
    await db.commit()
    await db.refresh(org)
    return org
