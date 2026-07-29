"""BaseClass (L3 神职) market API routes.

Read-only list endpoint for the phase-15f onboarding modal. The portal
needs to be able to enumerate the available 神职 templates so the user
can pick one when creating a new Employee — without this endpoint, the
portal would have to hard-code the list.

Auth: any authenticated user (read-only, no role gate).
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DB, CurrentUserDep
from app.core.openapi import add_error_responses
from app.core.pagination import OffsetPage, paginate_offset
from app.models.base_class import BaseClass
from app.schemas.base_class import BaseClassOut

router = APIRouter(prefix="/base-classes", tags=["BaseClasses"])
add_error_responses(router)


@router.get("", response_model=OffsetPage[BaseClassOut])
async def list_base_classes(
    db: DB,
    current_user: CurrentUserDep,
    limit: int = 50,
    offset: int = 0,
) -> OffsetPage:
    """List active BaseClass rows in ``created_at DESC`` order.

    The onboarding modal uses the first page to offer defaults; the
    marketplace UI uses pagination for older entries.
    """
    stmt = (
        select(BaseClass)
        .where(BaseClass.deleted_at.is_(None))
        .order_by(BaseClass.created_at.desc())
    )
    return await paginate_offset(db, stmt, offset, min(limit, 200))
