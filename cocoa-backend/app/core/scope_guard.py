"""Scope guards for scoped resources (v4.0 D15).

``system`` scope rows are platform presets: visible and usable, but general
users must not create / edit / delete them — the write path returns 4xx.
Preset scope changes are likewise forbidden.
"""

from __future__ import annotations

from app.core.errors import ForbiddenError

VALID_SCOPES = frozenset({"system", "org", "namespace"})


def ensure_scope_create_allowed(scope: str, *, resource: str) -> None:
    """Reject attempts to create ``system``-scoped rows via the API."""
    if scope == "system":
        raise ForbiddenError(
            "scope.system_create_forbidden",
            "errors.scope.system_create_forbidden",
            f"Cannot create a system-scoped {resource}; system rows are preset-only",
            details={"resource": resource, "scope": scope},
        )


def ensure_scope_mutable(current_scope: str, *, resource: str, row_id: str) -> None:
    """Reject update / delete of ``system``-scoped rows."""
    if current_scope == "system":
        raise ForbiddenError(
            "scope.system_readonly",
            "errors.scope.system_readonly",
            f"System-scoped {resource} '{row_id}' is preset and read-only",
            details={"resource": resource, "id": row_id},
        )
