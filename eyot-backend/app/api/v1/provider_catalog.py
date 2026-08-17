"""Provider catalog (models.dev presets) and per-provider model list (PRD-v3)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import CurrentUserDep
from app.core.errors import NotFoundError
from app.core.openapi import add_error_responses
from app.schemas.organization import (
    CatalogModelOut,
    CatalogModelsOut,
    ProviderCatalogEntryOut,
    ProviderCatalogListOut,
)
from app.services.llm.model_catalog import model_catalog

router = APIRouter(tags=["ProviderCatalog"])
add_error_responses(router)


@router.get("/provider-catalog", response_model=ProviderCatalogListOut)
async def list_provider_catalog(
    current_user: CurrentUserDep,
    q: str | None = Query(default=None),
) -> ProviderCatalogListOut:
    providers, degraded = await model_catalog.list_providers(q=q)
    return ProviderCatalogListOut(
        items=[
            ProviderCatalogEntryOut(
                id=p.id,
                name=p.name,
                api=p.api,
                inferred_request_format=p.inferred_request_format,
                model_count=p.model_count,
                doc=p.doc,
            )
            for p in providers
        ],
        degraded=degraded,
    )


@router.get(
    "/provider-catalog/{catalog_provider_id}/models",
    response_model=CatalogModelsOut,
)
async def list_catalog_provider_models(
    catalog_provider_id: str,
    current_user: CurrentUserDep,
    q: str | None = Query(default=None),
) -> CatalogModelsOut:
    entry = await model_catalog.get_provider(catalog_provider_id)
    if entry is None:
        raise NotFoundError(
            "provider_catalog.not_found",
            "errors.provider_catalog.not_found",
            f"Catalog provider '{catalog_provider_id}' not found",
        )
    models, degraded = await model_catalog.list_models_for_catalog_provider(
        catalog_provider_id
    )
    if q:
        ql = q.lower()
        models = [m for m in models if ql in m.id.lower() or ql in m.name.lower()]
    return CatalogModelsOut(
        items=[
            CatalogModelOut(
                id=m.id,
                name=m.name,
                provider=m.provider,
                context_length=m.context_length,
            )
            for m in models
        ],
        degraded=degraded,
    )
