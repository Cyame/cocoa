"""Tenant helpers — default Organization / Namespace resolution (PRD-v2)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.organization import Namespace, Organization


async def get_default_namespace(db: AsyncSession) -> Namespace:
    """Return the seeded ``default`` Namespace under org ``default``.

    Raises NotFoundError if the seed rows are missing (migration not applied).
    """
    org = (
        await db.execute(
            select(Organization).where(
                Organization.slug == "default",
                Organization.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if org is None:
        raise NotFoundError(
            "organization.not_found",
            "errors.organization.not_found",
            "Default organization not found — run alembic upgrade head",
        )

    ns = (
        await db.execute(
            select(Namespace).where(
                Namespace.org_id == org.id,
                Namespace.slug == "default",
                Namespace.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if ns is None:
        raise NotFoundError(
            "namespace.not_found",
            "errors.namespace.not_found",
            "Default namespace not found — run alembic upgrade head",
        )
    return ns


async def resolve_namespace_id(
    db: AsyncSession, namespace_id: str | None
) -> str:
    """Return *namespace_id*, or the seeded default when omitted."""
    if namespace_id:
        return namespace_id
    ns = await get_default_namespace(db)
    return ns.id
