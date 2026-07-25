"""In-memory per-IP fixed-window rate limiting.

P3 ships an in-memory implementation only; P8 replaces the counter store
with Redis so limits hold across replicas.
"""

import math
import time
from collections import defaultdict
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

WINDOW_SECONDS = 60
MAX_REQUESTS_PER_WINDOW = 100
# Entries idle for longer than this are purged lazily on each counted request.
CLEANUP_AGE_SECONDS = 120
# Only API traffic is rate-limited; /health, /docs, /redoc, /openapi.json stay exempt.
COUNTED_PATH_PREFIX = "/api/"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window rate limiter keyed by client IP. Counts only ``/api/`` paths."""

    def __init__(self, app: Any) -> None:
        super().__init__(app)
        # ip -> {"count": float, "window_start": float}; window starts on the IP's first request.
        self._counters: defaultdict[str, dict[str, float]] = defaultdict(
            lambda: {"count": 0.0, "window_start": time.time()}
        )

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Enforce the window for counted paths; everything else passes through untouched."""
        if request.scope["type"] != "http":
            return await call_next(request)

        try:
            return await self._handle(request, call_next)
        except Exception:
            # Middleware-internal failure: the app's CocoaError handler lives in
            # ExceptionMiddleware (inner layer) and never sees middleware exceptions,
            # so build the standard error envelope directly.
            return JSONResponse(
                status_code=500,
                content={
                    "error_code": "internal_error",
                    "message_key": "errors.internal",
                    "message": "Internal server error",
                    "details": None,
                    "request_id": getattr(request.state, "request_id", None),
                },
            )

    async def _handle(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not request.url.path.startswith(COUNTED_PATH_PREFIX):
            return await call_next(request)

        now = time.time()
        self._cleanup_expired(now)

        client_ip = request.client.host if request.client else "unknown"
        entry = self._counters[client_ip]

        # Window expired: start a fresh one anchored at this request.
        if now - entry["window_start"] >= WINDOW_SECONDS:
            entry["window_start"] = now
            entry["count"] = 0.0

        if entry["count"] >= MAX_REQUESTS_PER_WINDOW:
            retry_after = math.ceil(entry["window_start"] + WINDOW_SECONDS - now)
            return JSONResponse(
                status_code=429,
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Remaining": "0",
                },
                content={
                    "error_code": "rate_limit_exceeded",
                    "message_key": "errors.rate_limit_exceeded",
                    "message": "Rate limit exceeded",
                    "details": None,
                    "request_id": getattr(request.state, "request_id", None),
                },
            )

        entry["count"] += 1
        remaining = MAX_REQUESTS_PER_WINDOW - int(entry["count"])

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response

    def _cleanup_expired(self, now: float) -> None:
        """Drop window entries idle for longer than CLEANUP_AGE_SECONDS."""
        cutoff = now - CLEANUP_AGE_SECONDS
        expired_ips = [ip for ip, entry in self._counters.items() if entry["window_start"] < cutoff]
        for ip in expired_ips:
            del self._counters[ip]
