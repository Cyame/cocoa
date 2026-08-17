"""Passage neighbor helpers — duplex (undirected) by product lock.

DB stores one row per undirected pair with ``mode=dual``. Endpoints are
canonicalized by lexicographic membership id order (``from`` = lo, ``to`` = hi).
Click / request orientation does not matter.

Optional one-way ``mode=directed`` is deferred.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace import Passage

PASSAGE_MODE_DUAL = "dual"


def normalize_endpoints(membership_a: str, membership_b: str) -> tuple[str, str]:
    """Return ``(lo, hi)`` lexicographic membership-id order for a dual edge."""
    if membership_a <= membership_b:
        return membership_a, membership_b
    return membership_b, membership_a


async def find_active_passage_between(
    session: AsyncSession,
    workspace_id: str,
    membership_a: str,
    membership_b: str,
) -> Passage | None:
    """Return an active Passage linking *a* and *b* (either orientation)."""
    lo, hi = normalize_endpoints(membership_a, membership_b)
    # Prefer canonical row; also accept legacy reverse rows pre-migration.
    result = await session.execute(
        select(Passage)
        .where(
            Passage.workspace_id == workspace_id,
            Passage.is_active.is_(True),
            Passage.deleted_at.is_(None),
            or_(
                (Passage.from_membership_id == lo) & (Passage.to_membership_id == hi),
                (Passage.from_membership_id == hi) & (Passage.to_membership_id == lo),
            ),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def neighbor_membership_ids(
    session: AsyncSession,
    workspace_id: str,
    membership_id: str,
) -> list[str]:
    """Membership IDs connected to *membership_id* via an active duplex Passage."""
    rows = (
        await session.execute(
            select(Passage).where(
                Passage.workspace_id == workspace_id,
                Passage.is_active.is_(True),
                Passage.deleted_at.is_(None),
                or_(
                    Passage.from_membership_id == membership_id,
                    Passage.to_membership_id == membership_id,
                ),
            )
        )
    ).scalars().all()
    neighbors: list[str] = []
    for p in rows:
        other = (
            p.to_membership_id
            if p.from_membership_id == membership_id
            else p.from_membership_id
        )
        if other and other not in neighbors:
            neighbors.append(other)
    return neighbors
