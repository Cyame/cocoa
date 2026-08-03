"""ai_genes schemas (深海基因)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field


class AiGeneCreate(BaseModel):
    slug: str
    name: str
    tags: list[str] | None = None
    manifest: dict | None = None
    description: str | None = None
    scope: str = "org"
    organization_id: str | None = None
    namespace_id: str | None = None


class AiGeneUpdate(BaseModel):
    name: str | None = None
    tags: list[str] | None = None
    manifest: dict | None = None
    description: str | None = None


class AiGeneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    name: str
    tags: list | None = None
    manifest: dict | None = None
    description: str | None = None
    scope: str = "org"
    organization_id: str | None = None
    namespace_id: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def readonly(self) -> bool:
        return self.scope == "system"


class AiGeneAttachBaseClassRequest(BaseModel):
    base_class_id: str
