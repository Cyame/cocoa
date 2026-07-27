"""CorridorNode CRUD API routes.

A CorridorNode is a first-class canvas element (P9 Todo 8) — a named,
positioned anchor on the office topology that corridors can attach to.
It is **not** a member of the office; it exists so the P9 topology viz
can group several corridors at a single visual hub (mirrors
nodeskclaw's ``CorridorHex``).

Route prefix is ``/learning/corridor-nodes`` (P9 — shares the
``/learning`` namespace with P10's planned endpoints). P9.5 may
refactor to a dedicated ``/topology`` prefix.

Routes:
    GET    /api/v1/learning/corridor-nodes                 — list (viewer)
    GET    /api/v1/learning/corridor-nodes/{id}            — fetch one (viewer)
    POST   /api/v1/learning/corridor-nodes                 — create (editor)
    PATCH  /api/v1/learning/corridor-nodes/{id}            — update (editor)
    DELETE /api/v1/learning/corridor-nodes/{id}            — soft delete (editor)

List and fetch use ``require_office_role(..., "viewer")``; mutations
use ``require_office_role(..., "editor")``. The 409 conflict on
(office_id, posx, posy) is enforced by the partial unique index
``uq_corridor_nodes_office_pos`` and surfaces as a
:class:`ConflictError` via the standard ``IntegrityError`` mapping.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, CurrentUserDep
from app.core.errors import ConflictError, NotFoundError
from app.core.openapi import add_error_responses
from app.core.permissions import require_office_role
from app.models.corridor_node import CorridorNode, CorridorNodeStatus
from app.models.office import Office
from app.schemas.corridor_node import (
    CorridorNodeCreate,
    CorridorNodeListOut,
    CorridorNodeOut,
    CorridorNodeUpdate,
)

router = APIRouter(prefix="/learning/corridor-nodes", tags=["CorridorNodes"])
add_error_responses(router)


@router.get("", response_model=CorridorNodeListOut)
async def list_corridor_nodes(
    db: DB,
    current_user: CurrentUserDep,
    office_id: str = Query(..., description="Filter by office"),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = Query(None, description="Opaque cursor (created_at ISO)"),
) -> CorridorNodeListOut:
    """List active corridor nodes in an office, ordered by ``created_at`` ascending.

    Cursor pagination matches :func:`app.api.v1.events._encode_cursor`'s
    ISO timestamp scheme. The total count is included so the
    topology viz client can render a "5 of 12 nodes" badge.
    """
    await require_office_role(db, current_user.user_id, office_id, "viewer")

    base = (
        select(CorridorNode)
        .where(
            CorridorNode.office_id == office_id,
            CorridorNode.deleted_at.is_(None),
        )
        .order_by(CorridorNode.created_at, CorridorNode.id)
    )

    if cursor is not None:
        base = base.where(CorridorNode.created_at > cursor)

    result = await db.execute(base.limit(limit + 1))
    rows = list(result.scalars().all())
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor: str | None = items[-1].created_at.isoformat() if has_more and items else None

    total_result = await db.execute(
        select(func.count())
        .select_from(CorridorNode)
        .where(
            CorridorNode.office_id == office_id,
            CorridorNode.deleted_at.is_(None),
        )
    )
    total: int = total_result.scalar_one()

    return CorridorNodeListOut(
        items=[CorridorNodeOut.model_validate(item) for item in items],
        next_cursor=next_cursor,
        total=total,
    )


@router.get("/{corridor_node_id}", response_model=CorridorNodeOut)
async def get_corridor_node(
    corridor_node_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> CorridorNode:
    """Return a single corridor node by ID.

    Raises 404 if the node does not exist or has been soft-deleted.
    """
    node = await db.get(CorridorNode, corridor_node_id)
    if node is None or node.deleted_at is not None:
        raise NotFoundError(
            "corridor_node.not_found",
            "errors.corridor_node.not_found",
            f"CorridorNode '{corridor_node_id}' not found",
        )
    await require_office_role(db, current_user.user_id, node.office_id, "viewer")
    return node


@router.post("", response_model=CorridorNodeOut, status_code=status.HTTP_201_CREATED)
async def create_corridor_node(
    body: CorridorNodeCreate,
    db: DB,
    current_user: CurrentUserDep,
) -> CorridorNode:
    """Create a new corridor node.

    Raises 404 if the office does not exist.
    Raises 403 if the caller is not at least an editor of the office.
    Raises 409 if an active corridor node already exists at the same
    (office_id, posx, posy) cell (partial unique index
    ``uq_corridor_nodes_office_pos``).
    """
    office = await db.get(Office, body.office_id)
    if office is None or office.deleted_at is not None:
        raise NotFoundError(
            "office.not_found",
            "errors.office.not_found",
            f"Office '{body.office_id}' not found",
        )

    await require_office_role(db, current_user.user_id, body.office_id, "editor")

    node = CorridorNode(
        office_id=body.office_id,
        posx=body.posx,
        posy=body.posy,
        display_name=body.display_name,
        glow_color=body.glow_color,
        status=body.status,
        created_by=current_user.user_id,
    )
    db.add(node)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError(
            "corridor_node.position_taken",
            "errors.corridor_node.position_taken",
            f"Position ({body.posx}, {body.posy}) is already used in this office",
        )
    await db.refresh(node)
    return node


@router.patch("/{corridor_node_id}", response_model=CorridorNodeOut)
async def update_corridor_node(
    corridor_node_id: str,
    body: CorridorNodeUpdate,
    db: DB,
    current_user: CurrentUserDep,
) -> CorridorNode:
    """Partially update a corridor node.

    Only the fields provided in the request body are changed.
    Raises 404 if the node does not exist or has been soft-deleted.
    Raises 403 if the caller is not at least an editor of the office.
    Raises 409 if a position move collides with another active node.
    """
    node = await db.get(CorridorNode, corridor_node_id)
    if node is None or node.deleted_at is not None:
        raise NotFoundError(
            "corridor_node.not_found",
            "errors.corridor_node.not_found",
            f"CorridorNode '{corridor_node_id}' not found",
        )

    await require_office_role(db, current_user.user_id, node.office_id, "editor")

    update_data = body.model_dump(exclude_unset=True)
    if "status" in update_data:
        update_data["status"] = CorridorNodeStatus(update_data["status"]).value

    for key, value in update_data.items():
        setattr(node, key, value)

    try:
        await db.commit()
    except IntegrityError:
        # See the analogous comment in update_membership: read
        # candidate coords from the request body, not the ORM attribute
        # — the failed commit() invalidates the cache.
        conflict_posx = body.posx
        conflict_posy = body.posy
        await db.rollback()
        raise ConflictError(
            "corridor_node.position_taken",
            "errors.corridor_node.position_taken",
            f"Position ({conflict_posx}, {conflict_posy}) is already used in this office",
        )
    await db.refresh(node)
    return node


@router.delete("/{corridor_node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_corridor_node(
    corridor_node_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> None:
    """Soft-delete a corridor node.

    The record is marked as deleted but not physically removed.
    Any active corridor edges that referenced this node keep their
    FK pointers; the polymorphic CHECK constraint allows those edges
    to remain valid until they themselves are deleted, at which point
    referential integrity to the soft-deleted corridor_nodes row is
    still satisfied (Postgres does not enforce FK targets must be
    active — only that the row exists). P9.5 may add a hard
    constraint at the application layer to cascade-soft-delete edges
    that lost their only endpoint.
    Raises 404 if the node does not exist or has already been deleted.
    Raises 403 if the caller is not at least an editor of the office.
    """
    node = await db.get(CorridorNode, corridor_node_id)
    if node is None or node.deleted_at is not None:
        raise NotFoundError(
            "corridor_node.not_found",
            "errors.corridor_node.not_found",
            f"CorridorNode '{corridor_node_id}' not found",
        )

    await require_office_role(db, current_user.user_id, node.office_id, "editor")

    node.soft_delete()
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
