"""Meeting lifecycle action endpoints (v4.8) — start / end / cancel.

Shares the ``/meetings`` router prefix with :mod:`app.api.v1.meetings` and
reuses its permission / serialization helpers. ``start`` runs the M6 wake
matrix (:mod:`app.core.meeting_wake`) on every participant.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.api.deps import DB, CurrentUserDep, XOrgIdHeader
from app.api.v1.meetings import (
    get_meeting_or_404,
    meeting_out,
    participants_for,
    require_meeting_manage,
    require_transition,
)
from app.core.event_types import (
    MEETING_CANCELLED,
    MEETING_ENDED,
    MEETING_STARTED,
)
from app.core.events import emit
from app.core.meeting_wake import wake_meeting_participants
from app.core.openapi import add_error_responses
from app.models.meeting import MeetingStatus
from app.schemas.meeting import MeetingOut

router = APIRouter(prefix="/meetings", tags=["Meetings"])
add_error_responses(router)


@router.post("/{meeting_id}/start", response_model=MeetingOut)
async def start_meeting(
    meeting_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> MeetingOut:
    """Start a scheduled meeting and wake its participants (M6 matrix)."""
    meeting = await get_meeting_or_404(db, meeting_id)
    await require_meeting_manage(
        db,
        current_user.user_id,
        meeting.workspace_id,
        x_organization_id=x_organization_id,
    )
    require_transition(
        meeting,
        frozenset({MeetingStatus.scheduled.value}),
        MeetingStatus.active.value,
    )
    meeting.status = MeetingStatus.active.value

    participants = await participants_for(db, meeting.id)
    await wake_meeting_participants(db, meeting, participants)

    await emit(
        MEETING_STARTED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="meeting",
        resource_id=meeting.id,
        payload={
            "participant_count": len(participants),
            "scheduled_at": (
                meeting.scheduled_at.isoformat() if meeting.scheduled_at else None
            ),
        },
        session=db,
    )
    await db.commit()
    await db.refresh(meeting)
    return meeting_out(meeting, participants)


@router.post("/{meeting_id}/end", response_model=MeetingOut)
async def end_meeting(
    meeting_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> MeetingOut:
    """End an active meeting."""
    meeting = await get_meeting_or_404(db, meeting_id)
    await require_meeting_manage(
        db,
        current_user.user_id,
        meeting.workspace_id,
        x_organization_id=x_organization_id,
    )
    require_transition(
        meeting,
        frozenset({MeetingStatus.active.value}),
        MeetingStatus.ended.value,
    )
    meeting.status = MeetingStatus.ended.value
    meeting.ended_at = datetime.now(timezone.utc)
    await emit(
        MEETING_ENDED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="meeting",
        resource_id=meeting.id,
        session=db,
    )
    await db.commit()
    await db.refresh(meeting)
    participants = await participants_for(db, meeting.id)
    return meeting_out(meeting, participants)


@router.post("/{meeting_id}/cancel", response_model=MeetingOut)
async def cancel_meeting(
    meeting_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> MeetingOut:
    """Cancel a scheduled or active meeting."""
    meeting = await get_meeting_or_404(db, meeting_id)
    await require_meeting_manage(
        db,
        current_user.user_id,
        meeting.workspace_id,
        x_organization_id=x_organization_id,
    )
    require_transition(
        meeting,
        frozenset(
            {
                MeetingStatus.scheduled.value,
                MeetingStatus.active.value,
            }
        ),
        MeetingStatus.cancelled.value,
    )
    meeting.status = MeetingStatus.cancelled.value
    await emit(
        MEETING_CANCELLED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="meeting",
        resource_id=meeting.id,
        session=db,
    )
    await db.commit()
    await db.refresh(meeting)
    participants = await participants_for(db, meeting.id)
    return meeting_out(meeting, participants)
