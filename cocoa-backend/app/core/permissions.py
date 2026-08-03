"""Contract-atom permission checking (v4.0 — design §3.6).

Authorization truth lives on Contracts:

- ``OrganizationContract`` + ``organization_contract_genes`` — world-level grant
- ``NamespaceContract`` + ``namespace_contract_genes`` — namespace refinement
  (union-inherited on top of the Org grant)

Two layers:

- :func:`require_permission` — **pure function**: takes explicit ids, never
  reads Request / headers.
- :func:`require_workspace_permission` — route-layer helper: resolves the
  workspace's ancestors, optionally validates the ``X-Organization-Id``
  header, then delegates to :func:`require_permission`.

``is_super_admin`` remains the platform-level exception and bypasses atom
checks. Membership rows are presence/topology records, never an authz source.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError
from app.models.namespace_contract import NamespaceContract, NamespaceContractGene
from app.models.organization import Namespace
from app.models.organization_contract import (
    OrganizationContract,
    OrganizationContractGene,
)
from app.models.user import User
from app.models.user_gene import UserGene
from app.models.workspace import Workspace
from app.schemas.auth import CurrentUser


async def _resolve_org_ns(
    session: AsyncSession,
    *,
    organization_id: str | None,
    namespace_id: str | None,
    workspace_id: str | None,
) -> tuple[str | None, str | None]:
    """Resolve (organization_id, namespace_id) from the deepest given id."""
    org_id = organization_id
    ns_id = namespace_id
    if workspace_id is not None:
        workspace = await session.get(Workspace, workspace_id)
        if workspace is None or workspace.deleted_at is not None:
            raise NotFoundError(
                "workspace.not_found",
                "errors.workspace.not_found",
                f"Workspace '{workspace_id}' not found",
            )
        if ns_id is None:
            ns_id = workspace.namespace_id
    if ns_id is not None and org_id is None:
        namespace = await session.get(Namespace, ns_id)
        if namespace is None or namespace.deleted_at is not None:
            raise NotFoundError(
                "namespace.not_found",
                "errors.namespace.not_found",
                f"Namespace '{ns_id}' not found",
            )
        org_id = namespace.org_id
    return org_id, ns_id


async def list_grant_slugs(
    session: AsyncSession,
    user_id: str,
    *,
    organization_id: str | None,
    namespace_id: str | None = None,
) -> set[str]:
    """Union of atom slugs granted to *user_id* on the given org (+namespace)."""
    slugs: set[str] = set()
    if organization_id is not None:
        result = await session.execute(
            select(UserGene.slug)
            .select_from(OrganizationContract)
            .join(
                OrganizationContractGene,
                OrganizationContractGene.contract_id == OrganizationContract.id,
            )
            .join(UserGene, UserGene.id == OrganizationContractGene.user_gene_id)
            .where(
                OrganizationContract.organization_id == organization_id,
                OrganizationContract.user_id == user_id,
                OrganizationContract.deleted_at.is_(None),
                OrganizationContractGene.deleted_at.is_(None),
                UserGene.deleted_at.is_(None),
            )
        )
        slugs.update(result.scalars().all())
    if namespace_id is not None:
        result = await session.execute(
            select(UserGene.slug)
            .select_from(NamespaceContract)
            .join(
                NamespaceContractGene,
                NamespaceContractGene.contract_id == NamespaceContract.id,
            )
            .join(UserGene, UserGene.id == NamespaceContractGene.user_gene_id)
            .where(
                NamespaceContract.namespace_id == namespace_id,
                NamespaceContract.user_id == user_id,
                NamespaceContract.deleted_at.is_(None),
                NamespaceContractGene.deleted_at.is_(None),
                UserGene.deleted_at.is_(None),
            )
        )
        slugs.update(result.scalars().all())
    return slugs


async def list_user_grant_slugs(session: AsyncSession, user_id: str) -> set[str]:
    """Union of **all** atom slugs granted to a user across every contract."""
    slugs: set[str] = set()
    result = await session.execute(
        select(UserGene.slug)
        .select_from(OrganizationContract)
        .join(
            OrganizationContractGene,
            OrganizationContractGene.contract_id == OrganizationContract.id,
        )
        .join(UserGene, UserGene.id == OrganizationContractGene.user_gene_id)
        .where(
            OrganizationContract.user_id == user_id,
            OrganizationContract.deleted_at.is_(None),
            OrganizationContractGene.deleted_at.is_(None),
            UserGene.deleted_at.is_(None),
        )
    )
    slugs.update(result.scalars().all())
    result = await session.execute(
        select(UserGene.slug)
        .select_from(NamespaceContract)
        .join(
            NamespaceContractGene,
            NamespaceContractGene.contract_id == NamespaceContract.id,
        )
        .join(UserGene, UserGene.id == NamespaceContractGene.user_gene_id)
        .where(
            NamespaceContract.user_id == user_id,
            NamespaceContract.deleted_at.is_(None),
            NamespaceContractGene.deleted_at.is_(None),
            UserGene.deleted_at.is_(None),
        )
    )
    slugs.update(result.scalars().all())
    return slugs


async def require_permission(
    session: AsyncSession,
    user_id: str,
    permission_key: str,
    *,
    organization_id: str | None = None,
    namespace_id: str | None = None,
    workspace_id: str | None = None,
) -> None:
    """Raise unless *user_id* holds atom *permission_key* on the resource scope.

    Ancestors are resolved from the deepest id given. When
    *organization_id* is explicitly passed alongside a resolvable resource,
    it must match the resolved org (header/session consistency check).

    Super-admins bypass atom checks (platform exception, design §3.6).
    """
    user = await session.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise ForbiddenError(
            "auth.user_not_found",
            "errors.auth.user_not_found",
            f"User '{user_id}' not found",
            details={"user_id": user_id},
        )
    if user.is_super_admin:
        return

    org_id, ns_id = await _resolve_org_ns(
        session,
        organization_id=organization_id,
        namespace_id=namespace_id,
        workspace_id=workspace_id,
    )
    if organization_id is not None and org_id is not None and organization_id != org_id:
        raise ForbiddenError(
            "organization.mismatch",
            "errors.organization.mismatch",
            "X-Organization-Id does not match the resource's organization",
            details={"expected": org_id, "got": organization_id},
        )

    slugs = await list_grant_slugs(
        session, user_id, organization_id=org_id, namespace_id=ns_id
    )
    if permission_key not in slugs:
        raise ForbiddenError(
            "permission.denied",
            "errors.permission.denied",
            f"User '{user_id}' lacks permission '{permission_key}'",
            details={
                "user_id": user_id,
                "permission_key": permission_key,
                "organization_id": org_id,
                "namespace_id": ns_id,
                "workspace_id": workspace_id,
            },
        )


async def require_workspace_permission(
    session: AsyncSession,
    user_id: str,
    workspace_id: str,
    permission_key: str,
    *,
    x_organization_id: str | None = None,
) -> None:
    """Workspace-scoped check: resolve ancestors, then require the atom.

    *x_organization_id* comes from the ``X-Organization-Id`` header at the
    route layer; when present it must match the workspace's org (v4.0
    transitional: missing header falls back to the resolved org).
    """
    await require_permission(
        session,
        user_id,
        permission_key,
        workspace_id=workspace_id,
        organization_id=x_organization_id,
    )


def require_super_admin(current_user: CurrentUser) -> None:
    """Raise ForbiddenError unless the caller is a platform super-admin."""
    if not current_user.is_super_admin:
        raise ForbiddenError(
            "auth.super_admin_required",
            "errors.auth.super_admin_required",
            "Super-admin privileges required",
            details={"user_id": current_user.user_id},
        )
