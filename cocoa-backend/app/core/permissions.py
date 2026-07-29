"""Workspace-scoped permission checker for role-gated endpoints.

P6 provides a single entry point that every CentralHub, FornixFile,
Vault, and Memory endpoint calls before touching data.

Usage::

    from app.core.permissions import require_workspace_role

    membership = await require_workspace_role(db, current_user.user_id, workspace_id, "editor")
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError
from app.models.workspace import Membership
from app.schemas.auth import CurrentUser

ROLE_ORDER: dict[str, int] = {"viewer": 0, "editor": 1, "operator": 2, "owner": 3}


async def require_workspace_role(
    session: AsyncSession,
    user_id: str,
    workspace_id: str,
    min_role: str,
) -> Membership:
    """Verify *user_id* holds at least *min_role* in *workspace_id*.

    Returns the active Membership row on success.
    Raises :class:`ForbiddenError` when the user is not a member or
    their role is too low.
    """
    result = await session.execute(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.workspace_id == workspace_id,
            Membership.deleted_at.is_(None),
        )
    )
    membership = result.scalar_one_or_none()

    if membership is None:
        raise ForbiddenError(
            "workspace.not_member",
            "errors.workspace.not_member",
            f"User '{user_id}' is not a member of workspace '{workspace_id}'",
            details={"user_id": user_id, "workspace_id": workspace_id},
        )

    current_order = ROLE_ORDER.get(membership.role, -1)
    required_order = ROLE_ORDER.get(min_role, 999)

    if current_order < required_order:
        raise ForbiddenError(
            "workspace.insufficient_role",
            "errors.workspace.insufficient_role",
            f"User '{user_id}' has role '{membership.role}' but needs at least '{min_role}'",
            details={
                "user_id": user_id,
                "workspace_id": workspace_id,
                "current_role": membership.role,
                "required_role": min_role,
            },
        )

    return membership


def require_super_admin(current_user: CurrentUser) -> None:
    """Raise ForbiddenError unless the caller is a platform super-admin."""
    if not current_user.is_super_admin:
        raise ForbiddenError(
            "auth.super_admin_required",
            "errors.auth.super_admin_required",
            "Super-admin privileges required",
            details={"user_id": current_user.user_id},
        )
