"""Meeting API schemas (v4.8)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MeetingParticipantIn(BaseModel):
    membership_id: str
    role_in_meeting: str | None = None


class MeetingCreate(BaseModel):
    workspace_id: str
    title: str
    agenda: str | None = None
    scheduled_at: datetime
    participant_membership_ids: list[str] = []


class MeetingParticipantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    meeting_id: str
    membership_id: str
    role_in_meeting: str | None = None


class MeetingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    title: str
    agenda: str | None = None
    status: str
    scheduled_at: datetime
    ended_at: datetime | None = None
    created_by_user_id: str
    created_at: datetime
    updated_at: datetime | None = None
    participants: list[MeetingParticipantOut] = []
