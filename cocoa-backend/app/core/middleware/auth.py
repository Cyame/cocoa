"""Auth stub middleware: extracts the bearer token without validating it.

P3 ships a pass-through stub only — no request is ever rejected here.
Real JWT validation and 401/403 enforcement land in P4.
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class AuthMiddleware(BaseHTTPMiddleware):
    """Parse ``Authorization: Bearer <token>`` into ``request.state`` without validation."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Stash the raw token (or None) and a placeholder user_id on request.state."""
        if request.scope["type"] != "http":
            return await call_next(request)

        token: str | None = None
        authorization = request.headers.get("Authorization")
        if authorization:
            scheme, _, credentials = authorization.partition(" ")
            if scheme.lower() == "bearer" and credentials:
                token = credentials

        request.state.token = token
        request.state.user_id = None  # Stub: no validation until P4.

        return await call_next(request)
