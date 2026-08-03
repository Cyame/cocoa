"""Organization context resolution and scoped-resource visibility (v4.1).

v4.2 Knowledge: scoped rows may live at the workspace layer. ``validate_scope_fks``
enforces the H2 write-time matrix (system all-null; org requires organization_id;
namespace requires organization_id+namespace_id; workspace requires all three).
``scoped_visibility_clause`` gains an opt-in ``include_workspace`` flag: when the
caller is org-scoped, workspace rows of that org are also visible (they were
created with org ancestry validated at write time, and org_scope has no
workspace-membership helper — the least-invasive correct option). Existing
system/org/namespace callers are unchanged (flag defaults to ``False``).
"""

from __future__ import annotations

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError, ValidationError
from app.core.scope_guard import VALID_SCOPES
from app.models.organization import Organization
from app.models.organization_contract import OrganizationContract
from app.models.user import User


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
        user = await db.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise ForbiddenError(
                "auth.user_not_found",
                "errors.auth.user_not_found",
                f"User '{user_id}' not found",
                details={"user_id": user_id},
            )
        if not user.is_super_admin:
            contract = await db.execute(
                select(OrganizationContract.id).where(
                    OrganizationContract.user_id == user_id,
                    OrganizationContract.organization_id == org.id,
                    OrganizationContract.deleted_at.is_(None),
                )
            )
            if contract.scalar_one_or_none() is None:
                raise ForbiddenError(
                    "organization.not_a_member",
                    "errors.organization.not_a_member",
                    f"User '{user_id}' is not a member of organization '{org.id}'",
                    details={"user_id": user_id, "organization_id": org.id},
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


def scoped_visibility_clause(
    model, org_id: str | None, scope_filter: str | None, *, include_workspace: bool = False
):
    """SQLAlchemy filter for scoped rows visible to *org_id*.

    Callers must apply ``deleted_at IS NULL`` separately.

    ``include_workspace`` (opt-in, v4.2): when the caller is org-scoped, also
    expose workspace rows of that org. Workspace rows carry ``organization_id``
    validated at write time, so org-level filtering works without joins. When
    ``org_id`` is None (system-only), workspace rows are org-owned and never
    visible — the flag is ignored.
    """
    if org_id is None:
        visibility = model.scope == "system"
    else:
        workspace_branch = []
        if include_workspace:
            workspace_branch.append(
                and_(model.scope == "workspace", model.organization_id == org_id)
            )
        visibility = or_(
            model.scope == "system",
            and_(model.scope == "org", model.organization_id == org_id),
            and_(model.scope == "namespace", model.organization_id == org_id),
            *workspace_branch,
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
    workspace_id: str | None = None,
    current_org_id: str | None,
) -> tuple[str | None, str | None, str | None]:
    """Validate scope ↔ FK triple (B1 / H2). Raises ValidationError on mismatch.

    v4.2 H2 write-time matrix: system requires all null; org requires
    organization_id (ns/ws null); namespace requires organization_id +
    namespace_id (ws null); workspace requires all three.
    """
    if scope not in VALID_SCOPES:
        raise ValidationError(
            "scope.invalid",
            "errors.scope.invalid",
            f"Invalid scope '{scope}'",
            details={"scope": scope, "allowed": sorted(VALID_SCOPES)},
        )

    org_id = organization_id
    ns_id = namespace_id
    ws_id = workspace_id

    # current_org_id fallback only applies to org/namespace scopes; workspace
    # requires the client to supply all three ids explicitly.
    if scope in ("org", "namespace") and org_id is None and current_org_id is not None:
        org_id = current_org_id

    if scope == "system":
        if org_id is not None or ns_id is not None or ws_id is not None:
            raise ValidationError(
                "scope.fk_mismatch",
                "errors.scope.fk_mismatch",
                "system scope requires organization_id, namespace_id and workspace_id to be null",
                details={
                    "organization_id": org_id,
                    "namespace_id": ns_id,
                    "workspace_id": ws_id,
                },
            )
        return None, None, None

    if scope == "org":
        if org_id is None:
            raise ValidationError(
                "scope.organization_required",
                "errors.scope.organization_required",
                "organization_id is required for org scope",
            )
        if ns_id is not None or ws_id is not None:
            raise ValidationError(
                "scope.fk_mismatch",
                "errors.scope.fk_mismatch",
                "org scope requires namespace_id and workspace_id to be null",
                details={
                    "namespace_id": ns_id,
                    "workspace_id": ws_id,
                },
            )
        if current_org_id is not None and org_id != current_org_id:
            raise ValidationError(
                "scope.organization_mismatch",
                "errors.scope.organization_mismatch",
                "organization_id does not match current organization context",
            )
        return org_id, None, None

    if scope == "workspace":
        if org_id is None or ns_id is None or ws_id is None:
            raise ValidationError(
                "scope.workspace_ids_required",
                "errors.scope.workspace_ids_required",
                "organization_id, namespace_id and workspace_id are required for workspace scope",
                details={
                    "organization_id": org_id,
                    "namespace_id": ns_id,
                    "workspace_id": ws_id,
                },
            )
        if current_org_id is not None and org_id != current_org_id:
            raise ValidationError(
                "scope.organization_mismatch",
                "errors.scope.organization_mismatch",
                "organization_id does not match current organization context",
            )
        return org_id, ns_id, ws_id

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
    if ws_id is not None:
        raise ValidationError(
            "scope.fk_mismatch",
            "errors.scope.fk_mismatch",
            "namespace scope requires workspace_id to be null",
            details={"workspace_id": ws_id},
        )
    if current_org_id is not None and org_id != current_org_id:
        raise ValidationError(
            "scope.organization_mismatch",
            "errors.scope.organization_mismatch",
            "organization_id does not match current organization context",
        )
    return org_id, ns_id, None
