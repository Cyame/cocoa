"""FastAPI dependency-injection stubs shared by all API routers.

P3 ships three dependencies:

- ``get_db`` — yields an ``AsyncSession`` from the session factory, closed
  automatically by the context manager.
- ``get_current_user`` — ENV-gated stub: in ``dev`` every caller is a
  super-admin; elsewhere it raises ``UnauthorizedError`` until P4 wires real
  authentication. P4 replaces only this function body — the signature and
  the ``CurrentUser`` return model stay identical.
- ``get_pagination_params`` — limit/cursor/offset query params.

Each dependency also exports an ``Annotated`` type alias (``DB``,
``CurrentUserDep``, ``PaginationParams``) for clean endpoint signatures.
"""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session_factory
from app.core.errors import UnauthorizedError
from app.schemas.auth import CurrentUser


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session, closed automatically on request end."""
    async with get_session_factory()() as session:
        yield session


async def get_current_user(request: Request) -> CurrentUser:
    """Return the authenticated user (stub).

    In ``dev`` every request is treated as a super-admin. In any other
    environment authentication is not implemented yet and the request is
    rejected with 401. P4 replaces this body with real token verification.
    """
    if settings.ENV == "dev":
        return CurrentUser(
            user_id="dev-user",
            is_super_admin=True,
            token=getattr(request.state, "token", None),
        )
    raise UnauthorizedError(
        "auth.not_implemented",
        "errors.auth.not_implemented",
        "Authentication not implemented in this environment",
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
