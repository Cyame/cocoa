"""CentralHub brain-region schemas (frontal / brainstem / cerebellum)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FrontalLobeKanbanCreate(BaseModel):
    title: str
    description: str | None = None
    status: str = "todo"
    assignee_entity_id: str | None = None
    position: int = 0
    due_at: datetime | None = None


class FrontalLobeKanbanUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    assignee_entity_id: str | None = None
    position: int | None = None
    due_at: datetime | None = None


class FrontalLobeKanbanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    central_hub_id: str
    title: str
    description: str | None = None
    status: str
    assignee_entity_id: str | None = None
    position: int
    due_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None


class BrainstemScheduleCreate(BaseModel):
    name: str
    cron_expr: str
    action_payload: dict | None = None
    enabled: bool = True


class BrainstemScheduleUpdate(BaseModel):
    name: str | None = None
    cron_expr: str | None = None
    action_payload: dict | None = None
    enabled: bool | None = None


class BrainstemScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    central_hub_id: str
    name: str
    cron_expr: str
    action_payload: dict | None = None
    enabled: bool
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None


class CerebellumUpdate(BaseModel):
    """v4.3: cerebellum PATCH — operates on the Entity, not the legacy agent."""

    name: str | None = None
    system_prompt: str | None = None
    preset_slug: str | None = None


class CerebellumOut(BaseModel):
    """v4.3: cerebellum GET — Entity + Instance projection.

    ``status`` is derived from the workspace Instance lifecycle status.
    """

    model_config = ConfigDict(from_attributes=True)

    entity_id: str
    instance_id: str
    workspace_id: str
    name: str
    slug: str
    preset_slug: str | None = None
    system_prompt: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime | None = None


class CerebellumRestartOut(BaseModel):
    """v4.9.1: cerebellum restart response.

    ``status`` mirrors the re-deploy pipeline outcome (``deploying`` after a
    successful kick-off, ``failed`` when the deploy could not start).
    ``old_hash`` / ``new_hash`` are optional for schema backward
    compatibility with the pre-v4.9.1 status-bounce stub.
    """

    entity_id: str
    instance_id: str
    status: str
    restarted_at: datetime
    old_hash: str | None = None
    new_hash: str | None = None
