"""Messaging API routes.

P5 implements messaging endpoints.
"""

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, CurrentUserDep
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.openapi import add_error_responses
from app.core.pagination import OffsetPage, paginate_offset
from app.models.office import Membership, MembershipRole, Office
from app.schemas.membership import MembershipCreate, MembershipOut, MembershipUpdate

router = APIRouter(prefix="/messaging", tags=["Messaging"])
add_error_responses(router)


# ---------------------------------------------------------------------------
# Membership CRUD
# ---------------------------------------------------------------------------


@router.get("/memberships", response_model=OffsetPage[MembershipOut])
async def list_memberships(
    office_id: str = Query(...),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: DB = None,
    _current_user: CurrentUserDep = None,
) -> OffsetPage:
    """List active (non-deleted) memberships in an office with offset pagination."""
    query = (
        select(Membership)
        .where(Membership.deleted_at.is_(None), Membership.office_id == office_id)
        .order_by(Membership.created_at)
    )
    return await paginate_offset(db, query, offset, limit)


@router.get("/memberships/{membership_id}", response_model=MembershipOut)
async def get_membership(
    membership_id: str,
    db: DB = None,
    _current_user: CurrentUserDep = None,
) -> Membership:
    """Return a single membership by ID.

    Raises 404 if the membership does not exist or has been soft-deleted.
    """
    result = await db.get(Membership, membership_id)
    if result is None or result.deleted_at is not None:
        raise NotFoundError(
            "membership.not_found",
            "errors.membership.not_found",
            f"Membership '{membership_id}' not found",
        )
    return result


@router.post("/memberships", response_model=MembershipOut, status_code=status.HTTP_201_CREATED)
async def create_membership(
    body: MembershipCreate,
    db: DB = None,
    _current_user: CurrentUserDep = None,
) -> Membership:
    """Create a new membership or reactivate a soft-deleted one.

    Raises 404 if the office does not exist.
    Raises 409 if an active membership already exists for the same
    user or instance in this office.
    Raises 422 if neither (or both) of user_id and instance_id are provided.
    """
    office = await db.get(Office, body.office_id)
    if office is None or office.deleted_at is not None:
        raise NotFoundError(
            "office.not_found",
            "errors.office.not_found",
            f"Office '{body.office_id}' not found",
        )

    fk_condition = (
        Membership.user_id == body.user_id
        if body.user_id is not None
        else Membership.instance_id == body.instance_id
    )
    existing = (
        await db.execute(
            select(Membership).where(
                Membership.office_id == body.office_id,
                fk_condition,
            )
        )
    ).scalars().first()

    if existing is not None:
        if existing.deleted_at is None:
            raise ConflictError(
                "membership.duplicate",
                "errors.membership.duplicate",
                "Membership already exists for this user/instance in this office",
            )
        # Undelete — reactivate a soft-deleted membership
        existing.deleted_at = None
        existing.role = body.role
        existing.posx = body.posx
        existing.posy = body.posy
        await db.commit()
        await db.refresh(existing)
        return existing

    membership = Membership(
        office_id=body.office_id,
        user_id=body.user_id,
        instance_id=body.instance_id,
        posx=body.posx,
        posy=body.posy,
        role=body.role,
    )
    db.add(membership)
    try:
        await db.commit()
    except IntegrityError:
        # uq_memberships_office_pos (P9) rejects (office_id, posx, posy)
        # duplicates on insert or reactivate of an active membership.
        await db.rollback()
        raise ConflictError(
            "membership.position_taken",
            "errors.membership.position_taken",
            f"Position ({body.posx}, {body.posy}) is already used in this office",
        )
    await db.refresh(membership)
    return membership


@router.patch("/memberships/{membership_id}", response_model=MembershipOut)
async def update_membership(
    membership_id: str,
    body: MembershipUpdate,
    db: DB = None,
    current_user: CurrentUserDep = None,
) -> Membership:
    """Partially update a membership.

    Only the fields provided in the request body are changed.
    Promoting a member to owner requires the current user to already be
    an owner of the same office.
    Raises 404 if the membership does not exist or has been soft-deleted.
    Raises 403 if the caller attempts to promote to owner but is not an owner.
    """
    membership = await db.get(Membership, membership_id)
    if membership is None or membership.deleted_at is not None:
        raise NotFoundError(
            "membership.not_found",
            "errors.membership.not_found",
            f"Membership '{membership_id}' not found",
        )

    if body.role == "owner" and body.role != membership.role:
        owner_result = await db.execute(
            select(Membership).where(
                Membership.office_id == membership.office_id,
                Membership.user_id == current_user.user_id,
                Membership.role == MembershipRole.owner,
                Membership.deleted_at.is_(None),
            )
        )
        if owner_result.scalar_one_or_none() is None:
            raise ForbiddenError(
                "membership.not_owner",
                "errors.membership.not_owner",
                "Only existing owners can promote members to owner role",
            )

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(membership, key, value)

    try:
        await db.commit()
    except IntegrityError:
        # uq_memberships_office_pos (P9) rejects moves to an occupied pos.
        # Read conflict coords from the request body, not the membership
        # — commit() failure invalidates the ORM attribute cache, and
        # any membership.* access would raise DetachedInstanceError.
        conflict_posx = body.posx
        conflict_posy = body.posy
        await db.rollback()
        raise ConflictError(
            "membership.position_taken",
            "errors.membership.position_taken",
            f"Position ({conflict_posx}, {conflict_posy}) is already used in this office",
        )
    await db.refresh(membership)
    return membership


@router.delete("/memberships/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_membership(
    membership_id: str,
    db: DB = None,
    _current_user: CurrentUserDep = None,
) -> None:
    """Soft-delete a membership.

    The record is marked as deleted but not physically removed.
    The last owner of an office cannot be deleted to prevent orphan offices.
    Raises 404 if the membership does not exist.
    Raises 409 if the membership is the last owner.
    """
    membership = await db.get(Membership, membership_id)
    if membership is None or membership.deleted_at is not None:
        raise NotFoundError(
            "membership.not_found",
            "errors.membership.not_found",
            f"Membership '{membership_id}' not found",
        )

    # Prevent removal of the last owner
    if membership.role == MembershipRole.owner:
        result = await db.execute(
            select(func.count())
            .select_from(Membership)
            .where(
                Membership.office_id == membership.office_id,
                Membership.role == MembershipRole.owner,
                Membership.deleted_at.is_(None),
            )
        )
        owner_count: int = result.scalar_one()
        if owner_count <= 1:
            raise ConflictError(
                "membership.last_owner",
                "errors.membership.last_owner",
                "Cannot remove the last owner of an office",
            )

    membership.soft_delete()
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Corridor CRUD
# ---------------------------------------------------------------------------


from app.core.topology import check_acyclic  # noqa: E402
from app.models.office import Corridor  # noqa: E402
from app.schemas.corridor import CorridorCreate, CorridorOut, CorridorUpdate  # noqa: E402


@router.get("/corridors", response_model=OffsetPage[CorridorOut])
async def list_corridors(
    office_id: str = Query(...),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: DB = None,
    _current_user: CurrentUserDep = None,
) -> OffsetPage:
    """List active (non-deleted) corridors in an office with offset pagination."""
    query = (
        select(Corridor)
        .where(Corridor.deleted_at.is_(None), Corridor.office_id == office_id)
        .order_by(Corridor.created_at)
    )
    return await paginate_offset(db, query, offset, limit)


@router.get("/corridors/{corridor_id}", response_model=CorridorOut)
async def get_corridor(
    corridor_id: str,
    db: DB = None,
    _current_user: CurrentUserDep = None,
) -> Corridor:
    """Return a single corridor by ID.

    Raises 404 if the corridor does not exist or has been soft-deleted.
    """
    result = await db.get(Corridor, corridor_id)
    if result is None or result.deleted_at is not None:
        raise NotFoundError(
            "corridor.not_found",
            "errors.corridor.not_found",
            f"Corridor '{corridor_id}' not found",
        )
    return result


@router.post("/corridors", response_model=CorridorOut, status_code=status.HTTP_201_CREATED)
async def create_corridor(
    body: CorridorCreate,
    db: DB = None,
    _current_user: CurrentUserDep = None,
) -> Corridor:
    """Create a new corridor or reactivate a soft-deleted one.

    Endpoints are polymorphic (P9 Todo 8): each side is either a
    :class:`Membership` or a :class:`CorridorNode`. The Pydantic
    :class:`CorridorCreate` enforces "exactly one of the two endpoint
    columns on each side must be set" before the request reaches
    this handler.

    For membership-to-membership edges, validates that the new edge
    does not introduce a cycle in the office graph (P5 acyclicity
    contract is unchanged) and uses ``SELECT ... FOR UPDATE`` on the
    from-membership row to serialize concurrent edge creation within
    the implicit session transaction. Membership-to-node, node-to-
    membership, and node-to-node edges skip the acyclic check because
    corridor nodes are not principals and do not participate in
    message routing.

    Raises 404 if the office / from-membership does not exist.
    Raises 409 if an active corridor already exists between the same
    endpoints, or if adding the edge would create a cycle.
    """
    from app.models.corridor_node import CorridorNode

    if body.from_membership_id is not None:
        lock = await db.execute(
            select(Membership).where(
                Membership.id == body.from_membership_id,
                Membership.deleted_at.is_(None),
            ).with_for_update(),
        )
        if lock.scalar_one_or_none() is None:
            raise NotFoundError(
                "membership.not_found",
                "errors.membership.not_found",
                f"Membership '{body.from_membership_id}' not found",
            )
    else:
        node_lock = await db.execute(
            select(CorridorNode).where(
                CorridorNode.id == body.from_corridor_node_id,
                CorridorNode.deleted_at.is_(None),
            ).with_for_update(),
        )
        if node_lock.scalar_one_or_none() is None:
            raise NotFoundError(
                "corridor_node.not_found",
                "errors.corridor_node.not_found",
                f"CorridorNode '{body.from_corridor_node_id}' not found",
            )

    if body.to_membership_id is not None:
        to_lock = await db.execute(
            select(Membership).where(
                Membership.id == body.to_membership_id,
                Membership.deleted_at.is_(None),
            ).with_for_update(),
        )
        if to_lock.scalar_one_or_none() is None:
            raise NotFoundError(
                "membership.not_found",
                "errors.membership.not_found",
                f"Membership '{body.to_membership_id}' not found",
            )
    else:
        to_node_lock = await db.execute(
            select(CorridorNode).where(
                CorridorNode.id == body.to_corridor_node_id,
                CorridorNode.deleted_at.is_(None),
            ).with_for_update(),
        )
        if to_node_lock.scalar_one_or_none() is None:
            raise NotFoundError(
                "corridor_node.not_found",
                "errors.corridor_node.not_found",
                f"CorridorNode '{body.to_corridor_node_id}' not found",
            )

    # Check for existing edge (active or soft-deleted). Match the
    # full 4-column endpoint tuple so node-inclusive edges dedupe
    # against themselves; the legacy uq_corridors_active_edge index
    # only catches the M<->M triple.
    result = await db.execute(
        select(Corridor).where(
            Corridor.office_id == body.office_id,
            Corridor.from_membership_id == body.from_membership_id,
            Corridor.to_membership_id == body.to_membership_id,
            Corridor.from_corridor_node_id == body.from_corridor_node_id,
            Corridor.to_corridor_node_id == body.to_corridor_node_id,
        ),
    )
    existing = result.scalars().first()
    if existing is not None:
        if existing.deleted_at is None:
            raise ConflictError(
                "corridor.duplicate",
                "errors.corridor.duplicate",
                "Corridor already exists between these endpoints",
            )
        # Undelete and reactivate
        existing.deleted_at = None
        existing.is_active = True
        await db.commit()
        await db.refresh(existing)
        return existing

    # Acyclicity check is only defined over the membership graph;
    # corridor nodes are not message-routing principals.
    if body.from_membership_id is not None and body.to_membership_id is not None:
        acyclic = await check_acyclic(
            db, body.office_id, body.from_membership_id, body.to_membership_id,
        )
        if not acyclic:
            raise ConflictError(
                "corridor.would_create_cycle",
                "errors.corridor.would_create_cycle",
                "Adding this edge would create a cycle",
            )

    corridor = Corridor(
        office_id=body.office_id,
        from_membership_id=body.from_membership_id,
        to_membership_id=body.to_membership_id,
        from_corridor_node_id=body.from_corridor_node_id,
        to_corridor_node_id=body.to_corridor_node_id,
        is_active=True,
    )
    db.add(corridor)
    try:
        await db.commit()
    except IntegrityError:
        # Race against the unique index or polymorphic CHECK.
        await db.rollback()
        raise ConflictError(
            "corridor.duplicate",
            "errors.corridor.duplicate",
            "Corridor already exists between these endpoints",
        )
    await db.refresh(corridor)
    return corridor


@router.patch("/corridors/{corridor_id}", response_model=CorridorOut)
async def update_corridor(
    corridor_id: str,
    body: CorridorUpdate,
    db: DB = None,
    _current_user: CurrentUserDep = None,
) -> Corridor:
    """Partially update a corridor.

    Only the fields provided in the request body are changed.
    Raises 404 if the corridor does not exist or has been soft-deleted.
    """
    corridor = await db.get(Corridor, corridor_id)
    if corridor is None or corridor.deleted_at is not None:
        raise NotFoundError(
            "corridor.not_found",
            "errors.corridor.not_found",
            f"Corridor '{corridor_id}' not found",
        )

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(corridor, key, value)

    await db.commit()
    await db.refresh(corridor)
    return corridor


@router.delete("/corridors/{corridor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_corridor(
    corridor_id: str,
    db: DB = None,
    _current_user: CurrentUserDep = None,
) -> None:
    """Soft-delete a corridor.

    The record is marked as deleted but not physically removed.
    Raises 404 if the corridor does not exist.
    """
    corridor = await db.get(Corridor, corridor_id)
    if corridor is None or corridor.deleted_at is not None:
        raise NotFoundError(
            "corridor.not_found",
            "errors.corridor.not_found",
            f"Corridor '{corridor_id}' not found",
        )

    corridor.soft_delete()
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Message send endpoint
# ---------------------------------------------------------------------------


from app.core.directive_router import route_turn  # noqa: E402
from app.core.slash_parser import parse_turn  # noqa: E402
from app.schemas.messaging import MessageSend, MessageSendResult  # noqa: E402


@router.post("/messages", response_model=MessageSendResult, status_code=status.HTTP_200_OK)
async def send_message(
    body: MessageSend,
    db: DB = None,
    current_user: CurrentUserDep = None,
):
    turn = parse_turn(body.turn_text)
    directive_results = await route_turn(
        session=db,
        raw_text=body.turn_text,
        office_id=body.office_id,
        from_user_id=current_user.user_id,
    )
    return MessageSendResult(
        directives=[d.cmd for d in turn.directives],
        general_text=turn.general_text,
        results=[
            {
                "target_employee": r.target_employee,
                "cmd": r.cmd,
                "delivery": [
                    {"delivered": d.delivered, "reason": d.reason, "instance_id": d.instance_id}
                    for d in r.results
                ],
            }
            for r in directive_results
        ],
    )


# ---------- Meeting / Scheduled-task scaffold ----------


@router.post("/meetings", status_code=501)
async def create_meeting():
    return {
        "error_code": "not_implemented",
        "message_key": "errors.not_implemented",
        "message": "Meeting semantics deferred to later phase",
    }


@router.post("/scheduled-tasks", status_code=501)
async def create_scheduled_task():
    return {
        "error_code": "not_implemented",
        "message_key": "errors.not_implemented",
        "message": "Scheduled-task semantics deferred to later phase",
    }
