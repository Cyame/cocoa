"""Request logging middleware: inject request_id context and emit start/end lines.

Registered immediately before RequestIDMiddleware so it can read
``request.state.request_id`` (set by RequestIDMiddleware, which runs first
in execution order).  Every downstream handler/call automatically inherits
the ``request_id`` context variable.
"""

import time

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class LoggingMiddleware(BaseHTTPMiddleware):
    """Wrap every HTTP request in a ``logger.contextualize(request_id=...)`` block.

    This ensures that *all* log lines emitted during the request — including
    those from uvicorn, SQLAlchemy, auth, and business logic — carry the
    ``request_id`` in their ``extra`` dict.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.scope["type"] != "http":
            return await call_next(request)

        request_id: str = getattr(request.state, "request_id", "-")

        with logger.contextualize(request_id=request_id):
            start = time.monotonic()
            logger.info("http.request.start", extra={"method": request.method, "path": request.url.path})
            response = await call_next(request)
            duration_ms = (time.monotonic() - start) * 1000
            logger.info(
                "http.request.end",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 3),
                },
            )
            return response
