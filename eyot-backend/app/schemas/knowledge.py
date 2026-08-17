"""knowledge_entries / knowledge_dimensions schemas (v4.2).

Ownership ids are nullable and validated against ``scope`` at write time in
the API layer (H2 matrix). ``key`` (and dimension ``slug``) are normalized
to lowercase by the router before insert / update.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class KnowledgeEntryCreate(BaseModel):
    key: str
    title: str
    body: str
    dimension_id: str | None = None
    scope: str = "org"
    organization_id: str | None = None
    namespace_id: str | None = None
    workspace_id: str | None = None
    entity_id: str | None = None
    instance_id: str | None = None


class KnowledgeEntryUpdate(BaseModel):
    key: str | None = None
    title: str | None = None
    body: str | None = None
    dimension_id: str | None = None
    entity_id: str | None = None
    instance_id: str | None = None


class KnowledgeEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    key: str
    title: str
    body: str
    dimension_id: str | None = None
    scope: str = "org"
    organization_id: str | None = None
    namespace_id: str | None = None
    workspace_id: str | None = None
    entity_id: str | None = None
    instance_id: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class KnowledgeDimensionCreate(BaseModel):
    name: str
    slug: str | None = None
    description: str | None = None
    scope: str = "org"
    organization_id: str | None = None
    namespace_id: str | None = None
    workspace_id: str | None = None


class KnowledgeDimensionUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    description: str | None = None


class KnowledgeDimensionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    description: str | None = None
    scope: str = "org"
    organization_id: str | None = None
    namespace_id: str | None = None
    workspace_id: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
