"""M6 meeting participant wake matrix (v4.8).

Delivers a meeting notification to every participant's Instance via the v4.7
inject queue. Best-effort per participant: a failure emits
``meeting.participant_wake_failed`` and continues with the others. Delivery is
strictly through ``enqueue_inject`` — no third message bus.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime import start_runtime_for
from app.core.event_types import (
    MEETING_PARTICIPANT_NO_INSTANCE,
    MEETING_PARTICIPANT_WAKE_FAILED,
)
from app.core.events import emit
from app.core.harness_supervisor import supervisor
from app.core.inject_queue import enqueue_inject
from app.models.instance import Instance, InstanceStatus
from app.models.loop_state import InstanceLoopState, LoopStatus
from app.models.meeting import Meeting, MeetingParticipant
from app.models.workspace import Membership

_RESUME_LOOP_STATUSES = frozenset(
    {
        LoopStatus.failed.value,
        LoopStatus.interrupted.value,
        LoopStatus.paused.value,
        LoopStatus.completed.value,
    }
)


def meeting_payload(meeting: Meeting) -> dict:
    return {
        "meeting_id": meeting.id,
        "title": meeting.title,
        "agenda": meeting.agenda,
        "scheduled_at": (
            meeting.scheduled_at.isoformat() if meeting.scheduled_at else None
        ),
    }


def meeting_tldr(meeting: Meeting) -> str:
    text = f"Meeting: {meeting.title}" if meeting.title else "Meeting notification"
    return text[:200]


async def _wake_participant(
    db: AsyncSession, meeting: Meeting, participant: MeetingParticipant
) -> None:
    """Wake matrix for one participant Membership (best-effort, never raises)."""
    membership = await db.get(Membership, participant.membership_id)
    if membership is None or membership.deleted_at is not None:
        return
    if membership.instance_id is None:
        await _emit_no_instance(db, meeting, participant)
        return

    instance = await db.get(Instance, membership.instance_id)
    if instance is None or instance.deleted_at is not None:
        await _emit_no_instance(db, meeting, participant)
        return

    loop_result = await db.execute(
        select(InstanceLoopState).where(
            InstanceLoopState.instance_id == instance.id,
            InstanceLoopState.deleted_at.is_(None),
        )
    )
    loop_state = loop_result.scalars().first()
    loop_status = loop_state.loop_status if loop_state is not None else None

    payload = meeting_payload(meeting)
    tldr = meeting_tldr(meeting)

    if (
        instance.status == InstanceStatus.running.value
        and loop_status == LoopStatus.running.value
    ):
        await enqueue_inject(
            db,
            instance_id=instance.id,
            kind="collab_inject",
            delivery_mode="soft_inject",
            payload=payload,
            tldr=tldr,
        )
        return

    if (
        loop_status in _RESUME_LOOP_STATUSES
        or instance.status == InstanceStatus.pending.value
    ):
        try:
            if loop_state is None:
                loop_state = InstanceLoopState(
                    instance_id=instance.id, loop_status=LoopStatus.idle.value
                )
                db.add(loop_state)
                await db.flush()
            await supervisor.handle_resume(instance.id, db)
            await db.flush()
            await start_runtime_for(instance.id)
        except Exception as exc:  # noqa: BLE001 - best-effort per participant
            await emit(
                MEETING_PARTICIPANT_WAKE_FAILED,
                actor_type="system",
                resource_type="meeting",
                resource_id=meeting.id,
                payload={"instance_id": instance.id, "error": str(exc)},
                session=db,
            )
            return
        await enqueue_inject(
            db,
            instance_id=instance.id,
            kind="collab_inject",
            delivery_mode="wake",
            payload=payload,
            tldr=tldr,
        )
        return

    await enqueue_inject(
        db,
        instance_id=instance.id,
        kind="collab_inject",
        delivery_mode="wake",
        payload=payload,
        tldr=tldr,
    )


async def _emit_no_instance(
    db: AsyncSession, meeting: Meeting, participant: MeetingParticipant
) -> None:
    await emit(
        MEETING_PARTICIPANT_NO_INSTANCE,
        actor_type="system",
        resource_type="meeting",
        resource_id=meeting.id,
        payload={"membership_id": participant.membership_id},
        session=db,
    )


async def wake_meeting_participants(
    db: AsyncSession, meeting: Meeting, participants: list[MeetingParticipant]
) -> None:
    """Run the M6 wake matrix for every participant, continuing on failure."""
    for participant in participants:
        await _wake_participant(db, meeting, participant)
