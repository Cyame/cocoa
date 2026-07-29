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


class CerebellumAgentUpdate(BaseModel):
    system_prompt: str | None = None
    base_slug: str | None = None
    installed_genes: list | dict | None = None


class CerebellumAgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    central_hub_id: str
    name: str
    base_slug: str
    system_prompt: str | None = None
    loop_status: str
    heartbeat_at: datetime | None = None
    installed_genes: list | dict | None = None
    created_at: datetime
    updated_at: datetime | None = None


class CerebellumRestartOut(BaseModel):
    cerebellum_id: str
    loop_status: str
    restarted_at: datetime
