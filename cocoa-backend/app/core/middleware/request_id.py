"""Request ID middleware: assigns a unique ID to every incoming HTTP request."""

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a request ID to ``request.state.request_id`` and the ``X-Request-ID`` response header."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Generate the ID, stash it on request.state, and echo it on the response."""
        if request.scope["type"] != "http":
            return await call_next(request)

        # Python 3.12 stdlib has no uuid7; uuid4 is sufficient for correlation IDs.
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
