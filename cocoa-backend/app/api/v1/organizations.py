"""Organization + world Provider registry API (PRD-v2 / PRD-v3).

Routes:
    GET/PATCH /organizations/default
    CRUD      /organizations/default/providers
    POST      /organizations/default/providers/{id}/test
    POST      /organizations/default/providers/{id}/set-default
    GET/PATCH /organizations/default/system-hub
    GET/PATCH /organizations/default/cerebellum-defaults
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUserDep
from app.core.errors import ConflictError, NotFoundError
from app.core.openapi import add_error_responses
from app.core.permissions import require_super_admin
from app.models.base_class import BaseClass
from app.models.base_class_provider_default import BaseClassProviderDefault
from app.models.organization import Organization
from app.models.organization_provider import OrganizationProvider
from app.schemas.organization import (
    CatalogModelOut,
    CatalogModelsOut,
    CerebellumDefaultsOut,
    CerebellumDefaultsUpdate,
    OrganizationCreate,
    OrganizationOut,
    OrganizationProviderCreate,
    OrganizationProviderOut,
    OrganizationProviderUpdate,
    OrganizationUpdate,
    PreviewModelsRequest,
    ProviderOrigin,
    ProviderTestOut,
    SetDefaultOut,
    SetDefaultRequest,
    SetDefaultTarget,
    SystemHubOut,
    SystemHubUpdate,
)
from app.services.llm.llm_client import LLMError
from app.services.llm.model_catalog import model_catalog
from app.services.llm.org_provider import (
    build_llm_client_from_org_provider,
    fetch_custom_models,
    fetch_models_from_endpoint,
    slugify,
)

router = APIRouter(prefix="/organizations", tags=["Organizations"])
add_error_responses(router)


@router.post(
    "",
    response_model=OrganizationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_organization(
    body: OrganizationCreate,
    db: DB,
    current_user: CurrentUserDep,
) -> Organization:
    """Create a new Organization (world) — v4.0 audit B3 contract.

    Any authenticated user may create an organization (users with zero
    effective OrgContracts **bypass** ``can_manage_organization``; users who
    already hold contracts may also create additional worlds — abuse control
    is a later配额 concern, not this slice). The creator receives an
    :class:`OrganizationContract` with the full org|namespace|workspace atom
    seed set.
    """
    from app.core.gene_atoms import ORG_OWNER_ATOMS, ensure_atom_genes
    from app.core.org_contract import ensure_org_contract, grant_atoms

    existing = await db.execute(
        select(Organization).where(
            Organization.slug == body.slug,
            Organization.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(
            "organization.slug_taken",
            "errors.organization.slug_taken",
            f"Organization slug '{body.slug}' is already taken",
        )

    org = Organization(
        slug=body.slug,
        name=body.name,
        description=body.description,
    )
    db.add(org)
    await db.flush()

    await ensure_atom_genes(db)
    contract = await ensure_org_contract(
        db, organization_id=org.id, user_id=current_user.user_id
    )
    await grant_atoms(db, contract.id, ORG_OWNER_ATOMS)

    await db.commit()
    await db.refresh(org)
    return org


async def _get_default_org(db: DB) -> Organization:
    result = await db.execute(
        select(Organization).where(
            Organization.slug == "default",
            Organization.deleted_at.is_(None),
        )
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise NotFoundError(
            "organization.not_found",
            "errors.organization.not_found",
            "Default organization not found — run alembic upgrade head",
        )
    return org


async def _get_provider(db: DB, org_id: str, provider_id: str) -> OrganizationProvider:
    result = await db.execute(
        select(OrganizationProvider).where(
            OrganizationProvider.id == provider_id,
            OrganizationProvider.organization_id == org_id,
            OrganizationProvider.deleted_at.is_(None),
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise NotFoundError(
            "organization_provider.not_found",
            "errors.organization_provider.not_found",
            f"OrganizationProvider '{provider_id}' not found",
        )
    return row


@router.get("/default", response_model=OrganizationOut)
async def get_default_organization(
    db: DB,
    current_user: CurrentUserDep,
) -> Organization:
    return await _get_default_org(db)


@router.patch("/default", response_model=OrganizationOut)
async def update_default_organization(
    body: OrganizationUpdate,
    db: DB,
    current_user: CurrentUserDep,
) -> Organization:
    require_super_admin(current_user)
    org = await _get_default_org(db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(org, field, value)
    await db.commit()
    await db.refresh(org)
    return org


@router.get("/default/providers", response_model=list[OrganizationProviderOut])
async def list_providers(
    db: DB,
    current_user: CurrentUserDep,
    enabled: bool | None = Query(default=None),
) -> list[OrganizationProvider]:
    org = await _get_default_org(db)
    stmt = select(OrganizationProvider).where(
        OrganizationProvider.organization_id == org.id,
        OrganizationProvider.deleted_at.is_(None),
    )
    if enabled is not None:
        stmt = stmt.where(OrganizationProvider.enabled.is_(enabled))
    stmt = stmt.order_by(OrganizationProvider.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "/default/providers",
    response_model=OrganizationProviderOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_provider(
    body: OrganizationProviderCreate,
    db: DB,
    current_user: CurrentUserDep,
) -> OrganizationProvider:
    require_super_admin(current_user)
    org = await _get_default_org(db)

    if body.origin == ProviderOrigin.catalog:
        assert body.catalog_provider_id is not None
        existing = await db.execute(
            select(OrganizationProvider).where(
                OrganizationProvider.organization_id == org.id,
                OrganizationProvider.catalog_provider_id == body.catalog_provider_id,
                OrganizationProvider.origin == "catalog",
                OrganizationProvider.deleted_at.is_(None),
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ConflictError(
                "organization_provider.catalog_already_enabled",
                "errors.organization_provider.catalog_already_enabled",
                f"Catalog provider '{body.catalog_provider_id}' already enabled",
            )

        catalog_entry = await model_catalog.get_provider(body.catalog_provider_id)
        if catalog_entry is None:
            raise NotFoundError(
                "provider_catalog.not_found",
                "errors.provider_catalog.not_found",
                f"Catalog provider '{body.catalog_provider_id}' not found",
            )

        models, _ = await model_catalog.list_models_for_catalog_provider(
            body.catalog_provider_id
        )
        default_model = body.default_model
        if not default_model:
            default_model = models[0].id if models else "gpt-4o-mini"

        # Persist fetched model ids so later selectors don't re-hit the network.
        allowlist = body.models_allowlist
        if allowlist is None and models:
            allowlist = [m.id for m in models]

        name = body.name or catalog_entry.name
        slug = body.slug or slugify(body.catalog_provider_id)
        request_format = (
            body.request_format.value
            if body.request_format
            else catalog_entry.inferred_request_format
        )
        base_url = body.base_url if body.base_url is not None else catalog_entry.api

        row = OrganizationProvider(
            organization_id=org.id,
            origin="catalog",
            catalog_provider_id=body.catalog_provider_id,
            name=name,
            slug=slug,
            request_format=request_format,
            base_url=base_url,
            api_key_ref=body.api_key_ref,
            default_model=default_model,
            models_allowlist=allowlist,
            verify_ssl=body.verify_ssl,
            models_endpoint_mode=body.models_endpoint_mode.value,
            models_base_url=body.models_base_url,
            enabled=body.enabled,
        )
    else:
        slug = body.slug or slugify(body.name or "custom")
        slug_clash = await db.execute(
            select(OrganizationProvider).where(
                OrganizationProvider.organization_id == org.id,
                OrganizationProvider.slug == slug,
                OrganizationProvider.deleted_at.is_(None),
            )
        )
        if slug_clash.scalar_one_or_none() is not None:
            raise ConflictError(
                "organization_provider.slug_taken",
                "errors.organization_provider.slug_taken",
                f"Provider slug '{slug}' already taken",
            )
        assert body.request_format is not None
        assert body.default_model is not None
        assert body.name is not None
        row = OrganizationProvider(
            organization_id=org.id,
            origin="custom",
            catalog_provider_id=None,
            name=body.name,
            slug=slug,
            request_format=body.request_format.value,
            base_url=body.base_url,
            api_key_ref=body.api_key_ref,
            default_model=body.default_model,
            models_allowlist=body.models_allowlist,
            verify_ssl=body.verify_ssl,
            models_endpoint_mode=body.models_endpoint_mode.value,
            models_base_url=body.models_base_url,
            enabled=body.enabled,
        )

    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.get(
    "/default/providers/{provider_id}",
    response_model=OrganizationProviderOut,
)
async def get_provider(
    provider_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> OrganizationProvider:
    org = await _get_default_org(db)
    return await _get_provider(db, org.id, provider_id)


@router.patch(
    "/default/providers/{provider_id}",
    response_model=OrganizationProviderOut,
)
async def update_provider(
    provider_id: str,
    body: OrganizationProviderUpdate,
    db: DB,
    current_user: CurrentUserDep,
) -> OrganizationProvider:
    require_super_admin(current_user)
    org = await _get_default_org(db)
    row = await _get_provider(db, org.id, provider_id)
    data = body.model_dump(exclude_unset=True)
    if "request_format" in data and data["request_format"] is not None:
        data["request_format"] = data["request_format"].value
    if "models_endpoint_mode" in data and data["models_endpoint_mode"] is not None:
        data["models_endpoint_mode"] = data["models_endpoint_mode"].value
    for field, value in data.items():
        setattr(row, field, value)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete(
    "/default/providers/{provider_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_provider(
    provider_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> Response:
    require_super_admin(current_user)
    org = await _get_default_org(db)
    row = await _get_provider(db, org.id, provider_id)
    row.soft_delete()
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/default/providers/preview-models",
    response_model=CatalogModelsOut,
)
async def preview_provider_models(
    body: PreviewModelsRequest,
    db: DB,
    current_user: CurrentUserDep,
) -> CatalogModelsOut:
    """Call the provider /models endpoint (or models.dev for catalog) before save."""
    require_super_admin(current_user)
    await _get_default_org(db)

    if body.catalog_provider_id and not body.base_url:
        models, degraded = await model_catalog.list_models_for_catalog_provider(
            body.catalog_provider_id
        )
        # Prefer live /models when api + key are available.
        entry = await model_catalog.get_provider(body.catalog_provider_id)
        live_base = entry.api if entry is not None else None
        if live_base and body.api_key_ref:
            live_items, live_err = await fetch_models_from_endpoint(
                api_key_ref=body.api_key_ref,
                base_url=live_base,
                request_format=(
                    body.request_format.value
                    if body.request_format
                    else (entry.inferred_request_format if entry else "completion")
                ),
                verify_ssl=body.verify_ssl,
                models_endpoint_mode=body.models_endpoint_mode.value,
                models_base_url=body.models_base_url,
                provider_slug=body.catalog_provider_id,
            )
            if live_items and not live_err:
                return CatalogModelsOut(
                    items=[
                        CatalogModelOut(
                            id=i["id"],
                            name=i["name"],
                            provider=i["provider"],
                            context_length=i.get("context_length"),
                        )
                        for i in live_items
                    ],
                    degraded=False,
                )
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

    raw_items, error = await fetch_models_from_endpoint(
        api_key_ref=body.api_key_ref,
        base_url=body.base_url,
        request_format=body.request_format.value,
        verify_ssl=body.verify_ssl,
        models_endpoint_mode=body.models_endpoint_mode.value,
        models_base_url=body.models_base_url,
    )
    return CatalogModelsOut(
        items=[
            CatalogModelOut(
                id=i["id"],
                name=i["name"],
                provider=i["provider"],
                context_length=i.get("context_length"),
            )
            for i in raw_items
        ],
        error=error,
    )


@router.post(
    "/default/providers/{provider_id}/refresh-models",
    response_model=CatalogModelsOut,
)
async def refresh_provider_models(
    provider_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> CatalogModelsOut:
    """Re-fetch models and persist ids onto models_allowlist."""
    require_super_admin(current_user)
    org = await _get_default_org(db)
    row = await _get_provider(db, org.id, provider_id)

    error: str | None = None
    degraded = False
    items: list[CatalogModelOut] = []

    if row.origin == "catalog" and row.catalog_provider_id:
        # Prefer live /models when base_url + key work; else models.dev cache.
        if row.base_url:
            raw_items, error = await fetch_custom_models(row)
            if raw_items and not error:
                items = [
                    CatalogModelOut(
                        id=i["id"],
                        name=i["name"],
                        provider=i["provider"],
                        context_length=i.get("context_length"),
                    )
                    for i in raw_items
                ]
        if not items:
            models, degraded = await model_catalog.list_models_for_catalog_provider(
                row.catalog_provider_id
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
    else:
        raw_items, error = await fetch_custom_models(row)
        items = [
            CatalogModelOut(
                id=i["id"],
                name=i["name"],
                provider=i["provider"],
                context_length=i.get("context_length"),
            )
            for i in raw_items
        ]

    if items:
        row.models_allowlist = [i.id for i in items]
        if row.default_model not in row.models_allowlist:
            row.default_model = items[0].id
        await db.commit()
        await db.refresh(row)

    return CatalogModelsOut(
        items=items,
        degraded=degraded,
        default_model=row.default_model,
        error=error,
    )


@router.post(
    "/default/providers/{provider_id}/test",
    response_model=ProviderTestOut,
)
async def test_provider(
    provider_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> ProviderTestOut:
    require_super_admin(current_user)
    org = await _get_default_org(db)
    row = await _get_provider(db, org.id, provider_id)
    started = time.monotonic()
    try:
        client = build_llm_client_from_org_provider(row)
        resp = await client.complete(
            [{"role": "user", "content": "ping"}],
            max_tokens=8,
            temperature=0,
        )
        elapsed_ms = int((time.monotonic() - started) * 1000)
        detail = {
            "latency_ms": elapsed_ms,
            "model": resp.model,
            "preview": (resp.content or "")[:80],
        }
        row.last_test_status = "ok"
        row.last_test_detail = detail
        row.last_tested_at = datetime.now(timezone.utc)
        await db.commit()
        return ProviderTestOut(status="ok", detail=detail)
    except (LLMError, Exception) as exc:  # noqa: BLE001
        elapsed_ms = int((time.monotonic() - started) * 1000)
        detail = {"latency_ms": elapsed_ms, "error": str(exc)[:500]}
        row.last_test_status = "error"
        row.last_test_detail = detail
        row.last_tested_at = datetime.now(timezone.utc)
        await db.commit()
        return ProviderTestOut(status="error", detail=detail)


@router.post(
    "/default/providers/{provider_id}/set-default",
    response_model=SetDefaultOut,
)
async def set_default(
    provider_id: str,
    body: SetDefaultRequest,
    db: DB,
    current_user: CurrentUserDep,
) -> SetDefaultOut:
    require_super_admin(current_user)
    org = await _get_default_org(db)
    row = await _get_provider(db, org.id, provider_id)

    if body.target == SetDefaultTarget.system_hub:
        org.system_hub_provider_id = row.id
        org.system_hub_model = body.model
        await db.commit()
        return SetDefaultOut(
            target=body.target.value,
            provider_id=row.id,
            model=body.model,
        )

    if body.target == SetDefaultTarget.cerebellum:
        org.cerebellum_default_provider_id = row.id
        org.cerebellum_default_model = body.model
        await db.commit()
        return SetDefaultOut(
            target=body.target.value,
            provider_id=row.id,
            model=body.model,
        )

    # base_class
    ids = body.base_class_ids or []
    for bc_id in ids:
        bc = await db.execute(
            select(BaseClass).where(
                BaseClass.id == bc_id,
                BaseClass.deleted_at.is_(None),
            )
        )
        if bc.scalar_one_or_none() is None:
            raise NotFoundError(
                "base_class.not_found",
                "errors.base_class.not_found",
                f"BaseClass '{bc_id}' not found",
            )
        existing = await db.execute(
            select(BaseClassProviderDefault).where(
                BaseClassProviderDefault.base_class_id == bc_id,
                BaseClassProviderDefault.deleted_at.is_(None),
            )
        )
        binding = existing.scalar_one_or_none()
        if binding is None:
            db.add(
                BaseClassProviderDefault(
                    base_class_id=bc_id,
                    provider_id=row.id,
                    model=body.model,
                )
            )
        else:
            binding.provider_id = row.id
            binding.model = body.model
    await db.commit()
    return SetDefaultOut(
        target=body.target.value,
        provider_id=row.id,
        model=body.model,
        base_class_ids=ids,
    )


@router.get("/default/system-hub", response_model=SystemHubOut)
async def get_system_hub(
    db: DB,
    current_user: CurrentUserDep,
) -> SystemHubOut:
    org = await _get_default_org(db)
    return SystemHubOut(
        provider_id=org.system_hub_provider_id,
        model=org.system_hub_model,
        configured=bool(org.system_hub_provider_id and org.system_hub_model),
    )


@router.patch("/default/system-hub", response_model=SystemHubOut)
async def update_system_hub(
    body: SystemHubUpdate,
    db: DB,
    current_user: CurrentUserDep,
) -> SystemHubOut:
    require_super_admin(current_user)
    org = await _get_default_org(db)
    data = body.model_dump(exclude_unset=True)
    if "provider_id" in data:
        pid = data["provider_id"]
        if pid is not None:
            await _get_provider(db, org.id, pid)
        org.system_hub_provider_id = pid
    if "model" in data:
        org.system_hub_model = data["model"]
    await db.commit()
    await db.refresh(org)
    return SystemHubOut(
        provider_id=org.system_hub_provider_id,
        model=org.system_hub_model,
        configured=bool(org.system_hub_provider_id and org.system_hub_model),
    )


@router.get("/default/cerebellum-defaults", response_model=CerebellumDefaultsOut)
async def get_cerebellum_defaults(
    db: DB,
    current_user: CurrentUserDep,
) -> CerebellumDefaultsOut:
    org = await _get_default_org(db)
    return CerebellumDefaultsOut(
        provider_id=org.cerebellum_default_provider_id,
        model=org.cerebellum_default_model,
    )


@router.patch("/default/cerebellum-defaults", response_model=CerebellumDefaultsOut)
async def update_cerebellum_defaults(
    body: CerebellumDefaultsUpdate,
    db: DB,
    current_user: CurrentUserDep,
) -> CerebellumDefaultsOut:
    require_super_admin(current_user)
    org = await _get_default_org(db)
    data = body.model_dump(exclude_unset=True)
    if "provider_id" in data:
        pid = data["provider_id"]
        if pid is not None:
            await _get_provider(db, org.id, pid)
        org.cerebellum_default_provider_id = pid
    if "model" in data:
        org.cerebellum_default_model = data["model"]
    await db.commit()
    await db.refresh(org)
    return CerebellumDefaultsOut(
        provider_id=org.cerebellum_default_provider_id,
        model=org.cerebellum_default_model,
    )
