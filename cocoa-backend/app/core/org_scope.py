"""Organization context resolution and scoped-resource visibility (v4.1)."""

from __future__ import annotations

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.core.scope_guard import VALID_SCOPES
from app.models.organization import Organization
from app.models.organization_contract import OrganizationContract


async def resolve_current_org_id(
    db: AsyncSession,
    user_id: str,
    x_organization_id: str | None,
) -> str | None:
    """Resolve the active organization for list/write context.

    1) Explicit ``X-Organization-Id`` header — validate org exists.
    2) Else exactly one active OrganizationContract for the user.
    3) Else ``None`` (system-only visibility for lists).
    """
    if x_organization_id is not None:
        org = await db.get(Organization, x_organization_id)
        if org is None or org.deleted_at is not None:
            raise NotFoundError(
                "organization.not_found",
                "errors.organization.not_found",
                f"Organization '{x_organization_id}' not found",
            )
        return org.id

    result = await db.execute(
        select(OrganizationContract.organization_id)
        .where(
            OrganizationContract.user_id == user_id,
            OrganizationContract.deleted_at.is_(None),
        )
        .distinct()
    )
    org_ids = list(result.scalars().all())
    if len(org_ids) == 1:
        return org_ids[0]
    return None


def scoped_visibility_clause(model, org_id: str | None, scope_filter: str | None):
    """SQLAlchemy filter for scoped rows visible to *org_id*.

    Callers must apply ``deleted_at IS NULL`` separately.
    """
    if org_id is None:
        visibility = model.scope == "system"
    else:
        visibility = or_(
            model.scope == "system",
            and_(model.scope == "org", model.organization_id == org_id),
            and_(model.scope == "namespace", model.organization_id == org_id),
        )

    if scope_filter is not None:
        if scope_filter not in VALID_SCOPES:
            raise ValidationError(
                "scope.invalid",
                "errors.scope.invalid",
                f"Invalid scope filter '{scope_filter}'",
                details={"scope": scope_filter, "allowed": sorted(VALID_SCOPES)},
            )
        return and_(visibility, model.scope == scope_filter)
    return visibility


def validate_scope_fks(
    scope: str,
    organization_id: str | None,
    namespace_id: str | None,
    *,
    current_org_id: str | None,
) -> tuple[str | None, str | None]:
    """Validate scope ↔ FK triple (B1). Raises ValidationError on mismatch."""
    if scope not in VALID_SCOPES:
        raise ValidationError(
            "scope.invalid",
            "errors.scope.invalid",
            f"Invalid scope '{scope}'",
            details={"scope": scope, "allowed": sorted(VALID_SCOPES)},
        )

    org_id = organization_id
    ns_id = namespace_id

    if scope in ("org", "namespace") and org_id is None and current_org_id is not None:
        org_id = current_org_id

    if scope == "system":
        if org_id is not None or ns_id is not None:
            raise ValidationError(
                "scope.fk_mismatch",
                "errors.scope.fk_mismatch",
                "system scope requires organization_id and namespace_id to be null",
            )
        return None, None

    if scope == "org":
        if org_id is None:
            raise ValidationError(
                "scope.organization_required",
                "errors.scope.organization_required",
                "organization_id is required for org scope",
            )
        if ns_id is not None:
            raise ValidationError(
                "scope.fk_mismatch",
                "errors.scope.fk_mismatch",
                "org scope requires namespace_id to be null",
            )
        if current_org_id is not None and org_id != current_org_id:
            raise ValidationError(
                "scope.organization_mismatch",
                "errors.scope.organization_mismatch",
                "organization_id does not match current organization context",
            )
        return org_id, None

    # namespace scope
    if org_id is None:
        raise ValidationError(
            "scope.organization_required",
            "errors.scope.organization_required",
            "organization_id is required for namespace scope",
        )
    if ns_id is None:
        raise ValidationError(
            "scope.namespace_required",
            "errors.scope.namespace_required",
            "namespace_id is required for namespace scope",
        )
    if current_org_id is not None and org_id != current_org_id:
        raise ValidationError(
            "scope.organization_mismatch",
            "errors.scope.organization_mismatch",
            "organization_id does not match current organization context",
        )
    return org_id, ns_id
