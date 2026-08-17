"""Auth middleware: extracts and decodes the bearer token.

Token extraction (bearer parsing) + decode are **always** attempted, but
failures are **never** rejected at the middleware layer.  This lets anonymous
endpoints (``/health``, ``/docs``, ``/api/v1/auth/register``,
``/api/v1/auth/login``) pass through without credentials.

Real 401 enforcement happens in the ``get_current_user`` FastAPI dependency
inside ``app/api/deps.py``.
"""

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.core.security import decode_token


class AuthMiddleware(BaseHTTPMiddleware):
    """Parse ``Authorization: Bearer <token>`` and attempt JWT decode.

    On success ``request.state.user_id`` and ``request.state.jwt_payload`` are
    set from the token claims.  On failure both remain ``None`` — the request
    is **not** rejected here.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Extract the bearer token, decode it, and stash results on request.state."""
        if request.scope["type"] != "http":
            return await call_next(request)

        token: str | None = None
        authorization = request.headers.get("Authorization")
        if authorization:
            scheme, _, credentials = authorization.partition(" ")
            if scheme.lower() == "bearer" and credentials:
                token = credentials

        request.state.token = token
        request.state.user_id = None
        request.state.jwt_payload = None

        if token and settings.JWT_SECRET:
            try:
                payload = decode_token(token, settings.JWT_SECRET)
                request.state.user_id = payload.get("sub")
                request.state.jwt_payload = payload
            except Exception:
                logger.debug("AuthMiddleware: failed to decode token (passing through)")

        return await call_next(request)
