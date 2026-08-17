"""Structured error types and the standard error-response envelope.

Every API error returned by Eyot follows the same shape::

    {
        "error_code": "instance.not_found",
        "message_key": "errors.instance.not_found",
        "message": "Instance 'foo' not found",
        "details": {...} | null,
        "request_id": "..." | null
    }

``error_code`` is a stable machine identifier, ``message_key`` is the i18n
lookup key (lowercase dot-separated), and ``message`` is the fallback
human-readable text. ``request_id`` is injected by the exception handlers in
``app.main`` (which have access to the request), not by ``error_response``.
"""

from typing import Any

from fastapi.responses import JSONResponse


class EyotError(Exception):
    """Base class for all Eyot API errors."""

    def __init__(
        self,
        error_code: str,
        message_key: str,
        message: str,
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message_key = message_key
        self.message = message
        self.status_code = status_code
        self.details = details


class NotFoundError(EyotError):
    """Resource does not exist (404)."""

    def __init__(
        self,
        error_code: str,
        message_key: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(error_code, message_key, message, status_code=404, details=details)


class ValidationError(EyotError):
    """Domain-level validation failure (422)."""

    def __init__(
        self,
        error_code: str,
        message_key: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(error_code, message_key, message, status_code=422, details=details)


class UnauthorizedError(EyotError):
    """Missing or invalid credentials (401)."""

    def __init__(
        self,
        error_code: str,
        message_key: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(error_code, message_key, message, status_code=401, details=details)


class ForbiddenError(EyotError):
    """Authenticated but not allowed (403)."""

    def __init__(
        self,
        error_code: str,
        message_key: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(error_code, message_key, message, status_code=403, details=details)


class ConflictError(EyotError):
    """State conflict, e.g. duplicate key (409)."""

    def __init__(
        self,
        error_code: str,
        message_key: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(error_code, message_key, message, status_code=409, details=details)


class InternalError(EyotError):
    """Unexpected server-side failure (500)."""

    def __init__(
        self,
        error_code: str,
        message_key: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(error_code, message_key, message, status_code=500, details=details)


def error_response(exc: EyotError) -> JSONResponse:
    """Serialize an EyotError into the standard error envelope.

    ``request_id`` is NOT set here — this helper has no access to the
    request. The exception handlers in ``app.main`` inject it.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": exc.error_code,
            "message_key": exc.message_key,
            "message": exc.message,
            "details": exc.details,
        },
    )
