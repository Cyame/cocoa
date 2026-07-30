"""Model catalog for a world OrganizationProvider (PRD-v3).

GET /model-catalog?provider_id=… — prefer persisted models_allowlist;
otherwise catalog → models.dev / custom → remote /models.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import DB, CurrentUserDep
from app.api.v1.organizations import _get_default_org
from app.core.errors import NotFoundError
from app.core.openapi import add_error_responses
from app.models.organization_provider import OrganizationProvider
from app.schemas.organization import CatalogModelOut, CatalogModelsOut
from app.services.llm.model_catalog import model_catalog
from app.services.llm.org_provider import fetch_custom_models

router = APIRouter(tags=["ModelCatalog"])
add_error_responses(router)


@router.get("/model-catalog", response_model=CatalogModelsOut)
async def get_model_catalog(
    db: DB,
    current_user: CurrentUserDep,
    provider_id: str = Query(..., description="OrganizationProvider id"),
    q: str | None = Query(default=None),
    refresh: bool = Query(
        default=False,
        description="Bypass cached allowlist and re-fetch remote /models.dev",
    ),
) -> CatalogModelsOut:
    org = await _get_default_org(db)
    result = await db.execute(
        select(OrganizationProvider).where(
            OrganizationProvider.id == provider_id,
            OrganizationProvider.organization_id == org.id,
            OrganizationProvider.deleted_at.is_(None),
        )
    )
    provider = result.scalar_one_or_none()
    if provider is None:
        raise NotFoundError(
            "organization_provider.not_found",
            "errors.organization_provider.not_found",
            f"OrganizationProvider '{provider_id}' not found",
        )

    allowlist = provider.models_allowlist
    has_allowlist = isinstance(allowlist, list) and len(allowlist) > 0

    # Persisted list from setup-time fetch is the selection source of truth.
    if has_allowlist and not refresh:
        items = [
            CatalogModelOut(
                id=str(mid),
                name=str(mid),
                provider=provider.slug,
            )
            for mid in allowlist
        ]
        error = None
        degraded = False
    elif provider.origin == "catalog" and provider.catalog_provider_id:
        models, degraded = await model_catalog.list_models_for_catalog_provider(
            provider.catalog_provider_id
        )
        items = [
            CatalogModelOut(
                id=m.id,
                name=m.name,
                provider=m.provider,
                context_length=m.context_length,
            )
            for m in models
        ]
        error = None
        if has_allowlist:
            allow = {str(x) for x in allowlist}
            items = [i for i in items if i.id in allow]
    else:
        raw_items, error = await fetch_custom_models(provider)
        degraded = False
        items = [
            CatalogModelOut(
                id=i["id"],
                name=i["name"],
                provider=i["provider"],
                context_length=i.get("context_length"),
            )
            for i in raw_items
        ]
        if not any(i.id == provider.default_model for i in items):
            items.insert(
                0,
                CatalogModelOut(
                    id=provider.default_model,
                    name=provider.default_model,
                    provider=provider.slug,
                ),
            )

    if q:
        ql = q.lower()
        items = [i for i in items if ql in i.id.lower() or ql in i.name.lower()]

    return CatalogModelsOut(
        items=items,
        degraded=degraded if provider.origin == "catalog" else False,
        default_model=provider.default_model,
        error=error,
    )
