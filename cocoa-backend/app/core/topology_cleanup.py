"""Topology cleanup helpers — soft-delete passages when seats disappear.

Any membership soft-delete (user seat, instance seat, workspace wipe, …)
must clear incident Passage edges so the canvas and Composer never keep
zombie connections to deleted nodes.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace import Passage


async def soft_delete_passages_touching(
    session: AsyncSession,
    membership_ids: Sequence[str],
) -> int:
    """Soft-delete every active Passage that touches any of *membership_ids*.

    Returns the number of rows marked deleted (best-effort; 0 if empty input).
    """
    ids = [mid for mid in membership_ids if mid]
    if not ids:
        return 0
    result = await session.execute(
        update(Passage)
        .where(
            Passage.deleted_at.is_(None),
            or_(
                Passage.from_membership_id.in_(ids),
                Passage.to_membership_id.in_(ids),
            ),
        )
        .values(deleted_at=func.now(), is_active=False)
    )
    return int(result.rowcount or 0)
