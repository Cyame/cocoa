"""Request/response schemas for Entity CRUD (PRD-v2)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.slug import KebabSlug


class EntityCreate(BaseModel):
    name: str
    slug: KebabSlug
    namespace_id: str | None = None
    preset_slug: str | None = None
    display_name: str | None = None
    display_color: str | None = None
    system_prompt: str | None = None
    config_override: dict | None = None
    has_knowledge: list[str] | None = None
    # v4.3 D7: cerebellum flag — settable via API (partial-unique enforces
    # at most one per Namespace).
    is_cerebellum: bool = False


class EntityUpdate(BaseModel):
    slug: KebabSlug | None = None
    name: str | None = None
    preset_slug: str | None = None
    display_name: str | None = None
    display_color: str | None = None
    system_prompt: str | None = None
    config_override: dict | None = None
    has_knowledge: list[str] | None = None
    # v4.3 D7: flipping this on must still respect the one-per-namespace rule.
    is_cerebellum: bool | None = None


class EntityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    namespace_id: str
    name: str
    slug: str
    preset_slug: str | None = None
    display_name: str | None = None
    display_color: str | None = None
    system_prompt: str | None = None
    config_override: dict | None = None
    has_knowledge: list[str] | None = None
    migration_hash: str | None = None
    # v4.0: read-only aggregate DTO filled from the entity_capabilities
    # junction — not a DB column and never a write truth.
    capabilities: list | dict | None = None
    # v4.1: read-only AI-gene aggregate DTO filled from the entity_ai_genes
    # junction plus preset BaseClass inheritance — not a DB column and never
    # a write truth. Items are ``{"slug": ..., "source": "extra_added" |
    # "from_base_class"}``.
    ai_genes: list | dict | None = None
    is_cerebellum: bool = False
    created_at: datetime
    updated_at: datetime
