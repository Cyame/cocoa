"""Organization + world Provider schemas (PRD-v2 / PRD-v3)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    name: str
    system_hub_provider_id: str | None = None
    system_hub_model: str | None = None
    cerebellum_default_provider_id: str | None = None
    cerebellum_default_model: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class OrganizationUpdate(BaseModel):
    name: str | None = None


class ProviderOrigin(str, Enum):
    catalog = "catalog"
    custom = "custom"


class RequestFormat(str, Enum):
    completion = "completion"
    response = "response"
    anthropic = "anthropic"
    gemini = "gemini"


class ModelsEndpointMode(str, Enum):
    inherit = "inherit"
    separate = "separate"


class OrganizationProviderCreate(BaseModel):
    origin: ProviderOrigin
    catalog_provider_id: str | None = None
    name: str | None = None
    slug: str | None = None
    request_format: RequestFormat | None = None
    base_url: str | None = None
    api_key_ref: str
    default_model: str | None = None
    models_allowlist: list[str] | None = None
    verify_ssl: bool = True
    models_endpoint_mode: ModelsEndpointMode = ModelsEndpointMode.inherit
    models_base_url: str | None = None
    enabled: bool = True

    @model_validator(mode="after")
    def _validate_origin(self) -> OrganizationProviderCreate:
        if self.origin == ProviderOrigin.catalog:
            if not self.catalog_provider_id:
                raise ValueError("catalog_provider_id is required when origin=catalog")
        else:
            if not self.name:
                raise ValueError("name is required when origin=custom")
            if not self.slug:
                raise ValueError("slug is required when origin=custom")
            if not self.request_format:
                raise ValueError("request_format is required when origin=custom")
            if not self.default_model:
                raise ValueError("default_model is required when origin=custom")
            if not self.base_url:
                raise ValueError("base_url is required when origin=custom")
        if (
            self.models_endpoint_mode == ModelsEndpointMode.separate
            and not self.models_base_url
        ):
            raise ValueError("models_base_url is required when models_endpoint_mode=separate")
        return self


class OrganizationProviderUpdate(BaseModel):
    name: str | None = None
    request_format: RequestFormat | None = None
    base_url: str | None = None
    api_key_ref: str | None = None
    default_model: str | None = None
    models_allowlist: list[str] | None = None
    verify_ssl: bool | None = None
    models_endpoint_mode: ModelsEndpointMode | None = None
    models_base_url: str | None = None
    enabled: bool | None = None


class OrganizationProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    origin: str
    catalog_provider_id: str | None = None
    name: str
    slug: str
    request_format: str
    base_url: str | None = None
    api_key_ref: str
    default_model: str
    models_allowlist: list[str] | None = None
    verify_ssl: bool
    models_endpoint_mode: str
    models_base_url: str | None = None
    enabled: bool
    last_test_status: str | None = None
    last_tested_at: datetime | None = None
    last_test_detail: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime | None = None


class SetDefaultTarget(str, Enum):
    base_class = "base_class"
    system_hub = "system_hub"
    cerebellum = "cerebellum"


class SetDefaultRequest(BaseModel):
    target: SetDefaultTarget
    model: str
    base_class_ids: list[str] | None = Field(
        default=None,
        description="Required when target=base_class; multi-select 神职 ids",
    )

    @model_validator(mode="after")
    def _validate_target(self) -> SetDefaultRequest:
        if self.target == SetDefaultTarget.base_class and not self.base_class_ids:
            raise ValueError("base_class_ids required when target=base_class")
        return self


class SetDefaultOut(BaseModel):
    status: str = "ok"
    target: str
    provider_id: str
    model: str
    base_class_ids: list[str] | None = None


class SystemHubOut(BaseModel):
    provider_id: str | None = None
    model: str | None = None
    configured: bool = False


class SystemHubUpdate(BaseModel):
    provider_id: str | None = None
    model: str | None = None


class CerebellumDefaultsOut(BaseModel):
    provider_id: str | None = None
    model: str | None = None


class CerebellumDefaultsUpdate(BaseModel):
    provider_id: str | None = None
    model: str | None = None


class BaseClassProviderDefaultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    base_class_id: str
    provider_id: str
    model: str
    created_at: datetime
    updated_at: datetime | None = None


class BaseClassProviderDefaultUpdate(BaseModel):
    provider_id: str | None = None
    model: str | None = None


class ProviderCatalogEntryOut(BaseModel):
    id: str
    name: str
    api: str | None = None
    inferred_request_format: str
    model_count: int
    doc: str | None = None


class ProviderCatalogListOut(BaseModel):
    items: list[ProviderCatalogEntryOut]
    degraded: bool = False


class CatalogModelOut(BaseModel):
    id: str
    name: str
    provider: str
    context_length: int | None = None


class CatalogModelsOut(BaseModel):
    items: list[CatalogModelOut]
    degraded: bool = False
    default_model: str | None = None
    error: str | None = None


class ProviderTestOut(BaseModel):
    status: Literal["ok", "error"]
    detail: dict[str, Any] | None = None


class GenerateDescriptionRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None


class GenerateDescriptionOut(BaseModel):
    description: str
