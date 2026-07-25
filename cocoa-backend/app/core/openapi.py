"""OpenAPI metadata: standard error responses and helper utilities.

This module defines reusable OpenAPI error response schemas so that every
router can register consistent 401/403/404/422/500 responses without
duplicating descriptions and examples.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

_ERROR_ENVELOPE_EXAMPLE: dict[str, str | None] = {
    "error_code": "example.error",
    "message_key": "errors.example",
    "message": "Human-readable description of what went wrong",
    "details": None,
    "request_id": "abc12345-1234-1234-1234-123456789abc",
}

STANDARD_ERROR_RESPONSES: dict[int, dict[str, Any]] = {
    401: {
        "description": "Authentication required — missing or invalid credentials",
        "content": {
            "application/json": {
                "example": {**_ERROR_ENVELOPE_EXAMPLE,
                            "error_code": "auth.unauthorized",
                            "message_key": "errors.auth.unauthorized",
                            "message": "Authentication required"},
            }
        },
    },
    403: {
        "description": "Forbidden — valid credentials but insufficient permissions",
        "content": {
            "application/json": {
                "example": {**_ERROR_ENVELOPE_EXAMPLE,
                            "error_code": "auth.forbidden",
                            "message_key": "errors.auth.forbidden",
                            "message": "Insufficient permissions"},
            }
        },
    },
    404: {
        "description": "Resource not found",
        "content": {
            "application/json": {
                "example": {**_ERROR_ENVELOPE_EXAMPLE,
                            "error_code": "resource.not_found",
                            "message_key": "errors.resource.not_found",
                            "message": "The requested resource does not exist"},
            }
        },
    },
    422: {
        "description": "Validation error — request body or parameters are malformed",
        "content": {
            "application/json": {
                "example": {**_ERROR_ENVELOPE_EXAMPLE,
                            "error_code": "validation_error",
                            "message_key": "errors.validation",
                            "message": "Request validation failed",
                            "details": {"errors": []}},
            }
        },
    },
    500: {
        "description": "Internal server error — unexpected failure",
        "content": {
            "application/json": {
                "example": {**_ERROR_ENVELOPE_EXAMPLE,
                            "error_code": "internal_error",
                            "message_key": "errors.internal",
                            "message": "Internal server error"},
            }
        },
    },
}


def add_error_responses(router: APIRouter) -> None:
    """Register every standard error response on *router*.

    Call once per APIRouter (P4-P10) so that the generated OpenAPI schema
    advertises the error envelope shape for each status code.

    Usage::

        from fastapi import APIRouter
        from app.core.openapi import add_error_responses

        router = APIRouter()
        add_error_responses(router)

        @router.get("/widgets")
        async def list_widgets():
            ...
    """
    for status_code, response_def in STANDARD_ERROR_RESPONSES.items():
        router.responses[status_code] = response_def
