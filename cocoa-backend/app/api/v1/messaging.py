"""Messaging API routes.

P5 implements messaging endpoints.
"""

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, CurrentUserDep
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.openapi import add_error_responses
from app.core.pagination import OffsetPage, paginate_offset
from app.models.workspace import Membership, MembershipRole, Passage, Workspace
from app.schemas.membership import MembershipCreate, MembershipOut, MembershipUpdate

router = APIRouter(prefix="/messaging", tags=["Messaging"])
add_error_responses(router)


# ---------------------------------------------------------------------------
# Membership CRUD
# ---------------------------------------------------------------------------


@router.get("/memberships", response_model=OffsetPage[MembershipOut])
async def list_memberships(
    workspace_id: str = Query(...),
    kind: str | None = Query(None, pattern="^(user|instance)$"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: DB = None,
    _current_user: CurrentUserDep = None,
) -> OffsetPage:
    """List active memberships. ``kind=user`` = 觉醒者; ``kind=instance`` = 迷失者 seats."""
    query = (
        select(Membership)
        .where(Membership.deleted_at.is_(None), Membership.workspace_id == workspace_id)
        .order_by(Membership.created_at)
    )
    if kind == "user":
        query = query.where(Membership.user_id.is_not(None))
    elif kind == "instance":
        query = query.where(Membership.instance_id.is_not(None))
    page = await paginate_offset(db, query, offset, limit)
    items = await _enrich_memberships(db, page.items)
    return OffsetPage(items=items, total=page.total, limit=page.limit, offset=page.offset)


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

    Raises 404 if the workspace does not exist.
    Raises 409 if an active membership already exists for the same
    user or instance in this workspace.
    Raises 422 if neither (or both) of user_id and instance_id are provided.
    """
    workspace = await db.get(Workspace, body.workspace_id)
    if workspace is None or workspace.deleted_at is not None:
        raise NotFoundError(
            "workspace.not_found",
            "errors.workspace.not_found",
            f"Workspace '{body.workspace_id}' not found",
        )

    fk_condition = (
        Membership.user_id == body.user_id
        if body.user_id is not None
        else Membership.instance_id == body.instance_id
    )
    existing = (
        await db.execute(
            select(Membership).where(
                Membership.workspace_id == body.workspace_id,
                fk_condition,
            )
        )
    ).scalars().first()

    if existing is not None:
        if existing.deleted_at is None:
            raise ConflictError(
                "membership.duplicate",
                "errors.membership.duplicate",
                "Membership already exists for this user/instance in this workspace",
            )
        # Undelete — reactivate a soft-deleted membership
        existing.deleted_at = None
        existing.role = body.role
        existing.posx = body.posx
        existing.posy = body.posy
        if body.user_id is not None:
            from app.core.namespace_contract import ensure_namespace_contract

            await ensure_namespace_contract(
                db,
                namespace_id=workspace.namespace_id,
                user_id=body.user_id,
                role=body.role,
            )
        await db.commit()
        await db.refresh(existing)
        return existing

    if body.user_id is not None:
        from app.core.namespace_contract import ensure_namespace_contract

        await ensure_namespace_contract(
            db,
            namespace_id=workspace.namespace_id,
            user_id=body.user_id,
            role=body.role,
        )

    membership = Membership(
        workspace_id=body.workspace_id,
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
        # uq_memberships_workspace_pos (P9) rejects (workspace_id, posx, posy)
        # duplicates on insert or reactivate of an active membership.
        await db.rollback()
        raise ConflictError(
            "membership.position_taken",
            "errors.membership.position_taken",
            f"Position ({body.posx}, {body.posy}) is already used in this workspace",
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
    an owner of the same workspace.
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
                Membership.workspace_id == membership.workspace_id,
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
        # uq_memberships_workspace_pos (P9) rejects moves to an occupied pos.
        # Read conflict coords from the request body, not the membership
        # — commit() failure invalidates the ORM attribute cache, and
        # any membership.* access would raise DetachedInstanceError.
        conflict_posx = body.posx
        conflict_posy = body.posy
        await db.rollback()
        raise ConflictError(
            "membership.position_taken",
            "errors.membership.position_taken",
            f"Position ({conflict_posx}, {conflict_posy}) is already used in this workspace",
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
    The last owner of an workspace cannot be deleted to prevent orphan workspaces.
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
                Membership.workspace_id == membership.workspace_id,
                Membership.role == MembershipRole.owner,
                Membership.deleted_at.is_(None),
            )
        )
        owner_count: int = result.scalar_one()
        if owner_count <= 1:
            raise ConflictError(
                "membership.last_owner",
                "errors.membership.last_owner",
                "Cannot remove the last owner of an workspace",
            )

    membership.soft_delete()
    # Soft-delete passages that touch this seat so dead edges cannot block Composer.
    await db.execute(
        update(Passage)
        .where(
            Passage.deleted_at.is_(None),
            or_(
                Passage.from_membership_id == membership_id,
                Passage.to_membership_id == membership_id,
            ),
        )
        .values(deleted_at=func.now(), is_active=False)
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Passage CRUD
# ---------------------------------------------------------------------------


from app.core.topology import check_acyclic  # noqa: E402
from app.schemas.passage import PassageCreate, PassageOut, PassageUpdate  # noqa: E402


@router.get("/passages", response_model=OffsetPage[PassageOut])
async def list_passages(
    workspace_id: str = Query(...),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: DB = None,
    _current_user: CurrentUserDep = None,
) -> OffsetPage:
    """List active (non-deleted) passages in an workspace with offset pagination."""
    query = (
        select(Passage)
        .where(Passage.deleted_at.is_(None), Passage.workspace_id == workspace_id)
        .order_by(Passage.created_at)
    )
    return await paginate_offset(db, query, offset, limit)


@router.get("/passages/{passage_id}", response_model=PassageOut)
async def get_passage(
    passage_id: str,
    db: DB = None,
    _current_user: CurrentUserDep = None,
) -> Passage:
    """Return a single passage by ID.

    Raises 404 if the passage does not exist or has been soft-deleted.
    """
    result = await db.get(Passage, passage_id)
    if result is None or result.deleted_at is not None:
        raise NotFoundError(
            "passage.not_found",
            "errors.passage.not_found",
            f"Passage '{passage_id}' not found",
        )
    return result


@router.post("/passages", response_model=PassageOut, status_code=status.HTTP_201_CREATED)
async def create_passage(
    body: PassageCreate,
    db: DB = None,
    _current_user: CurrentUserDep = None,
) -> Passage:
    """Create a Membership↔Membership passage. CorridorNode edges are gone (PRD-v2)."""
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

    result = await db.execute(
        select(Passage).where(
            Passage.workspace_id == body.workspace_id,
            Passage.from_membership_id == body.from_membership_id,
            Passage.to_membership_id == body.to_membership_id,
        ),
    )
    existing = result.scalars().first()
    if existing is not None:
        if existing.deleted_at is None:
            raise ConflictError(
                "passage.duplicate",
                "errors.passage.duplicate",
                "Passage already exists between these endpoints",
            )
        existing.deleted_at = None
        existing.is_active = True
        await db.commit()
        await db.refresh(existing)
        return existing

    acyclic = await check_acyclic(
        db, body.workspace_id, body.from_membership_id, body.to_membership_id,
    )
    if not acyclic:
        raise ConflictError(
            "passage.would_create_cycle",
            "errors.passage.would_create_cycle",
            "Adding this edge would create a cycle",
        )

    passage = Passage(
        workspace_id=body.workspace_id,
        from_membership_id=body.from_membership_id,
        to_membership_id=body.to_membership_id,
        is_active=True,
        edge_meta=body.edge_meta,
    )
    db.add(passage)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError(
            "passage.duplicate",
            "errors.passage.duplicate",
            "Passage already exists between these endpoints",
        )
    await db.refresh(passage)
    return passage


@router.patch("/passages/{passage_id}", response_model=PassageOut)
async def update_passage(
    passage_id: str,
    body: PassageUpdate,
    db: DB = None,
    _current_user: CurrentUserDep = None,
) -> Passage:
    """Partially update a passage.

    Only the fields provided in the request body are changed.
    Raises 404 if the passage does not exist or has been soft-deleted.
    """
    passage = await db.get(Passage, passage_id)
    if passage is None or passage.deleted_at is not None:
        raise NotFoundError(
            "passage.not_found",
            "errors.passage.not_found",
            f"Passage '{passage_id}' not found",
        )

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(passage, key, value)

    await db.commit()
    await db.refresh(passage)
    return passage


@router.delete("/passages/{passage_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_passage(
    passage_id: str,
    db: DB = None,
    _current_user: CurrentUserDep = None,
) -> None:
    """Soft-delete a passage.

    The record is marked as deleted but not physically removed.
    Raises 404 if the passage does not exist.
    """
    passage = await db.get(Passage, passage_id)
    if passage is None or passage.deleted_at is not None:
        raise NotFoundError(
            "passage.not_found",
            "errors.passage.not_found",
            f"Passage '{passage_id}' not found",
        )

    passage.soft_delete()
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
        workspace_id=body.workspace_id,
        from_user_id=current_user.user_id,
    )
    return MessageSendResult(
        directives=[d.cmd for d in turn.directives],
        general_text=turn.general_text,
        results=[
            {
                "target_entity": r.target_entity,
                "cmd": r.cmd,
                "delivery": [
                    {
                        "delivered": d.delivered,
                        "reason": d.reason,
                        "instance_id": d.instance_id,
                        "turn_id": d.turn_id,
                    }
                    for d in r.results
                ],
            }
            for r in directive_results
        ],
    )


# ---------- Meeting / Scheduled-task scaffold ----------


async def _enrich_memberships(db: DB, memberships: list) -> list[MembershipOut]:
    """Attach entity_slug/name for instance seats (topology @slug)."""
    from app.models.entity import Entity
    from app.models.instance import Instance

    instance_ids = [m.instance_id for m in memberships if m.instance_id]
    inst_map: dict[str, Instance] = {}
    if instance_ids:
        rows = (
            await db.execute(
                select(Instance).where(
                    Instance.id.in_(instance_ids),
                    Instance.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        inst_map = {i.id: i for i in rows}
    entity_ids = [i.entity_id for i in inst_map.values()]
    ent_map: dict[str, Entity] = {}
    if entity_ids:
        rows = (
            await db.execute(
                select(Entity).where(
                    Entity.id.in_(entity_ids),
                    Entity.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        ent_map = {e.id: e for e in rows}

    out: list[MembershipOut] = []
    for m in memberships:
        base = MembershipOut.model_validate(m)
        if m.instance_id and m.instance_id in inst_map:
            ent = ent_map.get(inst_map[m.instance_id].entity_id)
            if ent is not None:
                base = base.model_copy(
                    update={
                        "entity_slug": ent.slug,
                        "entity_name": ent.display_name or ent.name,
                    }
                )
        out.append(base)
    return out


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
