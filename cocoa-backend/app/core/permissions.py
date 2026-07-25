"""Office-scoped permission checker for role-gated endpoints.

P6 provides a single entry point that every Blackboard, BlackboardFile,
Vault, and Memory endpoint calls before touching data.

Usage::

    from app.core.permissions import require_office_role

    membership = await require_office_role(db, current_user.user_id, office_id, "editor")
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError
from app.models.office import Membership

ROLE_ORDER: dict[str, int] = {"viewer": 0, "editor": 1, "owner": 2}


async def require_office_role(
    session: AsyncSession,
    user_id: str,
    office_id: str,
    min_role: str,
) -> Membership:
    """Verify *user_id* holds at least *min_role* in *office_id*.

    Returns the active Membership row on success.
    Raises :class:`ForbiddenError` when the user is not a member or
    their role is too low.
    """
    result = await session.execute(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.office_id == office_id,
            Membership.deleted_at.is_(None),
        )
    )
    membership = result.scalar_one_or_none()

    if membership is None:
        raise ForbiddenError(
            "office.not_member",
            "errors.office.not_member",
            f"User '{user_id}' is not a member of office '{office_id}'",
            details={"user_id": user_id, "office_id": office_id},
        )

    current_order = ROLE_ORDER.get(membership.role, -1)
    required_order = ROLE_ORDER.get(min_role, 999)

    if current_order < required_order:
        raise ForbiddenError(
            "office.insufficient_role",
            "errors.office.insufficient_role",
            f"User '{user_id}' has role '{membership.role}' but needs at least '{min_role}'",
            details={
                "user_id": user_id,
                "office_id": office_id,
                "current_role": membership.role,
                "required_role": min_role,
            },
        )

    return membership
