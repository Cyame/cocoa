"""Corridor acyclicity check via BFS.

P2 Corridor model permits arbitrary (from, to) edge pairs in the DB layer;
acyclicity is enforced at the P5 service layer here.
"""

from collections import deque

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.office import Corridor


async def check_acyclic(
    session: AsyncSession,
    office_id: str,
    from_id: str,
    to_id: str,
) -> bool:
    """Return True if adding edge from_id -> to_id keeps the graph acyclic.

    A self-loop (from_id == to_id) is always a cycle.
    Otherwise, BFS from to_id along active corridor edges; if from_id is
    reachable, the new edge would create a cycle.
    """
    if from_id == to_id:
        return False  # Self-loop is a trivial cycle
    visited: set[str] = {to_id}
    queue = deque([to_id])

    while queue:
        current = queue.popleft()
        # Find all edges coming OUT of current (active + not deleted)
        result = await session.execute(
            select(Corridor.to_membership_id).where(
                Corridor.office_id == office_id,
                Corridor.from_membership_id == current,
                Corridor.is_active.is_(True),
                Corridor.deleted_at.is_(None),
            )
        )
        neighbors = [row[0] for row in result.all()]
        for neighbor in neighbors:
            if neighbor == from_id:
                return False  # Would create a cycle
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)

    return True  # No cycle detected
