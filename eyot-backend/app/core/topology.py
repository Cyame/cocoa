"""Passage acyclicity check via undirected BFS.

Passages are duplex by product lock: an edge connects both endpoints regardless
of stored ``from`` / ``to`` order. Adding an edge between two memberships already
in the same connected component would create a cycle.
"""

from collections import deque

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace import Passage


async def check_acyclic(
    session: AsyncSession,
    workspace_id: str,
    from_id: str,
    to_id: str,
) -> bool:
    """Return True if adding an undirected edge from_id—to_id keeps the graph acyclic.

    A self-loop is always a cycle. Otherwise BFS from ``to_id`` along active
    duplex passages; if ``from_id`` is reachable, the new edge would close a cycle.
    """
    if from_id == to_id:
        return False

    visited: set[str] = {to_id}
    queue: deque[str] = deque([to_id])

    while queue:
        current = queue.popleft()
        result = await session.execute(
            select(Passage.from_membership_id, Passage.to_membership_id).where(
                Passage.workspace_id == workspace_id,
                Passage.is_active.is_(True),
                Passage.deleted_at.is_(None),
                or_(
                    Passage.from_membership_id == current,
                    Passage.to_membership_id == current,
                ),
            )
        )
        for a, b in result.all():
            neighbor = b if a == current else a
            if neighbor == from_id:
                return False
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)

    return True
