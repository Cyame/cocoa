"""Meeting API routes (v4.8) — CRUD + shared permission/serialization helpers.

Three endpoints under ``/api/v1/meetings``: POST create (scheduled), GET list
(``?workspace_id=``, offset page), GET ``{id}`` (with participants). Lifecycle
actions (start / end / cancel) live in :mod:`app.api.v1.meetings_actions` on
the same router prefix, mirroring the ``instances`` / ``harness`` split.

Authorization is ``can_manage_meetings`` **or** ``can_edit_workspace``
(reads additionally accept ``can_view_workspace``).
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUserDep, XOrgIdHeader
from app.core.errors import CocoaError, ConflictError, ForbiddenError, NotFoundError
from app.core.event_types import MEETING_CREATED
from app.core.events import emit
from app.core.openapi import add_error_responses
from app.core.pagination import OffsetPage, paginate_offset
from app.core.permissions import require_workspace_permission
from app.models.meeting import Meeting, MeetingParticipant, MeetingStatus
from app.models.workspace import Membership
from app.schemas.meeting import (
    MeetingCreate,
    MeetingOut,
    MeetingParticipantOut,
)

router = APIRouter(prefix="/meetings", tags=["Meetings"])
add_error_responses(router)


async def require_any_permission(
    db: DB,
    user_id: str,
    workspace_id: str,
    atoms: tuple[str, ...],
    *,
    x_organization_id: str | None,
) -> None:
    """Require at least one of *atoms* on the workspace scope.

    ``require_workspace_permission`` already bypasses atom checks for
    super-admins; trying each atom in order preserves the workspace/org
    ancestry resolution while implementing OR semantics.
    """
    last_error: ForbiddenError | None = None
    for atom in atoms:
        try:
            await require_workspace_permission(
                db,
                user_id,
                workspace_id,
                atom,
                x_organization_id=x_organization_id,
            )
            return
        except ForbiddenError as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


async def require_meeting_read(
    db: DB, user_id: str, workspace_id: str, *, x_organization_id: str | None
) -> None:
    await require_any_permission(
        db,
        user_id,
        workspace_id,
        ("can_manage_meetings", "can_edit_workspace", "can_view_workspace"),
        x_organization_id=x_organization_id,
    )


async def require_meeting_manage(
    db: DB, user_id: str, workspace_id: str, *, x_organization_id: str | None
) -> None:
    await require_any_permission(
        db,
        user_id,
        workspace_id,
        ("can_manage_meetings", "can_edit_workspace"),
        x_organization_id=x_organization_id,
    )


async def get_meeting_or_404(db: DB, meeting_id: str) -> Meeting:
    result = await db.execute(
        select(Meeting).where(
            Meeting.id == meeting_id,
            Meeting.deleted_at.is_(None),
        )
    )
    meeting = result.scalar_one_or_none()
    if meeting is None:
        raise NotFoundError(
            "meeting.not_found",
            "errors.meeting.not_found",
            f"Meeting '{meeting_id}' not found",
        )
    return meeting


async def participants_for(db: DB, meeting_id: str) -> list[MeetingParticipant]:
    result = await db.execute(
        select(MeetingParticipant)
        .where(
            MeetingParticipant.meeting_id == meeting_id,
            MeetingParticipant.deleted_at.is_(None),
        )
        .order_by(MeetingParticipant.created_at.asc())
    )
    return list(result.scalars().all())


def meeting_out(
    meeting: Meeting, participants: list[MeetingParticipant]
) -> MeetingOut:
    return MeetingOut(
        id=meeting.id,
        workspace_id=meeting.workspace_id,
        title=meeting.title,
        agenda=meeting.agenda,
        status=meeting.status,
        scheduled_at=meeting.scheduled_at,
        ended_at=meeting.ended_at,
        created_by_user_id=meeting.created_by_user_id,
        created_at=meeting.created_at,
        updated_at=meeting.updated_at,
        participants=[
            MeetingParticipantOut.model_validate(p) for p in participants
        ],
    )


def require_transition(
    meeting: Meeting, allowed: frozenset[str], new_status: str
) -> None:
    """Enforce the status whitelist; invalid transitions raise 409."""
    if meeting.status not in allowed:
        raise ConflictError(
            "meeting.invalid_transition",
            "errors.meeting.invalid_transition",
            f"Cannot transition meeting '{meeting.id}' from "
            f"'{meeting.status}' to '{new_status}'",
            details={"from": meeting.status, "to": new_status},
        )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.post("", response_model=MeetingOut, status_code=status.HTTP_201_CREATED)
async def create_meeting(
    body: MeetingCreate,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> MeetingOut:
    await require_meeting_manage(
        db,
        current_user.user_id,
        body.workspace_id,
        x_organization_id=x_organization_id,
    )

    member_ids = list(dict.fromkeys(body.participant_membership_ids))
    if member_ids:
        result = await db.execute(
            select(Membership).where(
                Membership.id.in_(member_ids),
                Membership.workspace_id == body.workspace_id,
                Membership.deleted_at.is_(None),
            )
        )
        valid = {m.id for m in result.scalars().all()}
        missing = [mid for mid in member_ids if mid not in valid]
        if missing:
            raise CocoaError(
                "meeting.membership_not_in_workspace",
                "errors.meeting.membership_not_in_workspace",
                "One or more participant memberships do not belong to this "
                "workspace",
                status_code=400,
                details={"membership_ids": missing},
            )

    meeting = Meeting(
        workspace_id=body.workspace_id,
        title=body.title,
        agenda=body.agenda,
        status=MeetingStatus.scheduled.value,
        scheduled_at=body.scheduled_at,
        created_by_user_id=current_user.user_id,
    )
    db.add(meeting)
    await db.flush()

    participants: list[MeetingParticipant] = []
    for mid in member_ids:
        participant = MeetingParticipant(
            meeting_id=meeting.id, membership_id=mid
        )
        db.add(participant)
        participants.append(participant)

    await emit(
        MEETING_CREATED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="meeting",
        resource_id=meeting.id,
        payload={
            "workspace_id": meeting.workspace_id,
            "title": meeting.title,
            "participant_count": len(participants),
        },
        session=db,
    )
    await db.commit()
    await db.refresh(meeting)
    for p in participants:
        await db.refresh(p)
    return meeting_out(meeting, participants)


@router.get("", response_model=OffsetPage[MeetingOut])
async def list_meetings(
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
    workspace_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> OffsetPage:
    stmt = select(Meeting).where(Meeting.deleted_at.is_(None))
    if workspace_id is not None:
        await require_meeting_read(
            db,
            current_user.user_id,
            workspace_id,
            x_organization_id=x_organization_id,
        )
        stmt = stmt.where(Meeting.workspace_id == workspace_id)
    else:
        stmt = stmt.where(
            Meeting.workspace_id.in_(
                select(Membership.workspace_id).where(
                    Membership.user_id == current_user.user_id,
                    Membership.deleted_at.is_(None),
                )
            )
        )
    stmt = stmt.order_by(Meeting.created_at.desc())
    page = await paginate_offset(db, stmt, offset, limit)
    return OffsetPage(
        items=[meeting_out(m, []) for m in page.items],
        offset=page.offset,
        limit=page.limit,
        total=page.total,
    )


@router.get("/{meeting_id}", response_model=MeetingOut)
async def get_meeting(
    meeting_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> MeetingOut:
    meeting = await get_meeting_or_404(db, meeting_id)
    await require_meeting_read(
        db,
        current_user.user_id,
        meeting.workspace_id,
        x_organization_id=x_organization_id,
    )
    participants = await participants_for(db, meeting.id)
    return meeting_out(meeting, participants)
