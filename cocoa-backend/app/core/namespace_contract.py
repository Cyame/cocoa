"""Ensure NamespaceContract (契印) helpers — PRD-v3.4 / v4.0."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.namespace_contract import NamespaceContract


async def ensure_namespace_contract(
    db: AsyncSession,
    *,
    namespace_id: str,
    user_id: str,
) -> NamespaceContract:
    """Return active contract, creating one if missing (atoms granted separately)."""
    result = await db.execute(
        select(NamespaceContract).where(
            NamespaceContract.namespace_id == namespace_id,
            NamespaceContract.user_id == user_id,
            NamespaceContract.deleted_at.is_(None),
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    contract = NamespaceContract(
        namespace_id=namespace_id,
        user_id=user_id,
    )
    db.add(contract)
    await db.flush()
    return contract
