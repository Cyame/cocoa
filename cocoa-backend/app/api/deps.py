"""FastAPI dependency-injection stubs shared by all API routers.

P3 ships three dependencies:

- ``get_db`` — yields an ``AsyncSession`` from the session factory, closed
  automatically by the context manager.
- ``get_current_user`` — decodes the JWT from the ``Authorization`` header,
  looks up the user in the database, and returns a ``CurrentUser``. Invalid
  or missing tokens raise ``UnauthorizedError``.
- ``get_pagination_params`` — limit/cursor/offset query params.

Each dependency also exports an ``Annotated`` type alias (``DB``,
``CurrentUserDep``, ``PaginationParams``) for clean endpoint signatures.
"""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Header, Query, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session_factory
from app.core.errors import EyotError, UnauthorizedError
from app.core.org_scope import resolve_current_org_id
from app.core.security import decode_token
from app.models.user import User
from app.schemas.auth import CurrentUser

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session, closed automatically on request end."""
    async with get_session_factory()() as session:
        yield session


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """Return the authenticated user from the JWT in the Authorization header.

    The token is first tried from ``request.state.token`` (set by
    AuthMiddleware), then from the ``Authorization`` header via HTTPBearer.
    """
    token: str | None = getattr(request.state, "token", None)
    if not token and credentials is not None:
        token = credentials.credentials
    if not token:
        raise UnauthorizedError(
            "auth.token_missing",
            "errors.auth.token_missing",
            "Authentication required",
        )

    try:
        payload = decode_token(token, settings.JWT_SECRET)
    except JWTError:
        raise UnauthorizedError(
            "auth.token_invalid",
            "errors.auth.token_invalid",
            "Invalid or expired token",
        )

    user_id: str = payload.get("sub", "")
    if not user_id:
        raise UnauthorizedError(
            "auth.token_invalid",
            "errors.auth.token_invalid",
            "Invalid token payload",
        )

    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise UnauthorizedError(
            "auth.user_not_found",
            "errors.auth.user_not_found",
            "User not found",
        )

    return CurrentUser(
        user_id=user.id,
        is_super_admin=user.is_super_admin,
        token=token,
    )


async def get_pagination_params(
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = Query(None),
    offset: int = Query(0, ge=0),
) -> dict:
    """Parse standard pagination query params."""
    return {"limit": limit, "cursor": cursor, "offset": offset}


DB = Annotated[AsyncSession, Depends(get_db)]
CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
PaginationParams = Annotated[dict, Depends(get_pagination_params)]
XOrgIdHeader = Annotated[str | None, Header(alias="X-Organization-Id")]


async def get_current_org(
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader,
) -> str:
    """Resolve the active organization id from the ``X-Organization-Id`` header.

    Delegates validation to :func:`resolve_current_org_id` (raises 404 for a
    missing org, 403 for a non-member). When no header is supplied and the
    user holds zero or multiple active contracts, no org context can be
    resolved — raise 400.
    """
    org_id = await resolve_current_org_id(
        db, current_user.user_id, x_organization_id
    )
    if org_id is None:
        raise EyotError(
            "organization.context_required",
            "errors.organization.context_required",
            "Unable to resolve an organization context — set X-Organization-Id "
            "or hold exactly one OrganizationContract",
            status_code=400,
        )
    return org_id


CurrentOrg = Annotated[str, Depends(get_current_org)]
