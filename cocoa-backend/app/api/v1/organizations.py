"""Organization + world Provider registry API (PRD-v2 / PRD-v3).

Routes:
    GET/PATCH /organizations/default
    CRUD      /organizations/default/providers (+ test/set-default/
               preview-models/refresh-models, system-hub, cerebellum-defaults)
    CRUD      /organizations/{org_id}/providers — org-scoped twins of the
               default-org provider lanes (v4.3 review; writes require
               can_manage_organization, reads require membership)
    CRUD      /organizations/{org_id}/members — world contracts (世界契印)
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import NoReturn

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import exists, or_, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, CurrentUserDep
from app.core.errors import (
    CocoaError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.core.gene_atoms import ATOM_CATALOG, ORG_OWNER_ATOMS, ensure_atom_genes
from app.core.openapi import add_error_responses
from app.core.org_contract import ensure_org_contract, grant_atoms
from app.core.pagination import OffsetPage, paginate_offset
from app.core.permissions import (
    list_grant_slugs,
    require_permission,
    require_super_admin,
)
from app.models.base_class import BaseClass
from app.models.base_class_provider_default import BaseClassProviderDefault
from app.models.entity import Entity
from app.models.instance import Instance
from app.models.junctions import EntityAiGene, EntityCapability
from app.models.knowledge import KnowledgeDimension, KnowledgeEntry
from app.models.namespace_contract import NamespaceContract, NamespaceContractGene
from app.models.organization import Namespace, Organization
from app.models.organization_contract import (
    OrganizationContract,
    OrganizationContractGene,
)
from app.models.organization_provider import OrganizationProvider
from app.models.user import User
from app.models.user_gene import UserGene
from app.models.workspace import Membership, Passage, Workspace
from app.schemas.organization import (
    CatalogModelOut,
    CatalogModelsOut,
    CerebellumDefaultsOut,
    CerebellumDefaultsUpdate,
    OrganizationCreate,
    OrganizationMemberAtomRef,
    OrganizationMemberAtomsUpdate,
    OrganizationMemberCreate,
    OrganizationMemberOut,
    OrganizationMemberUserRef,
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
        use_proxy=body.use_proxy,
        proxy_host=body.proxy_host,
        proxy_port=body.proxy_port,
        proxy_username=body.proxy_username,
        proxy_password=body.proxy_password,
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


# Shared handler bodies for both route families. The `/default/*` routes
# below are super-admin-gated aliases; `/organizations/{org_id}/...` twins
# gate writes on can_manage_organization.


async def _list_providers(
    db: DB, org: Organization, enabled: bool | None
) -> list[OrganizationProvider]:
    stmt = select(OrganizationProvider).where(
        OrganizationProvider.organization_id == org.id,
        OrganizationProvider.deleted_at.is_(None),
    )
    if enabled is not None:
        stmt = stmt.where(OrganizationProvider.enabled.is_(enabled))
    stmt = stmt.order_by(OrganizationProvider.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _create_provider(
    db: DB, org: Organization, body: OrganizationProviderCreate
) -> OrganizationProvider:
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


async def _update_provider(
    db: DB, org: Organization, provider_id: str, body: OrganizationProviderUpdate
) -> OrganizationProvider:
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


async def _delete_provider(db: DB, org: Organization, provider_id: str) -> None:
    row = await _get_provider(db, org.id, provider_id)
    row.soft_delete()
    await db.commit()


async def _preview_provider_models(
    db: DB, body: PreviewModelsRequest
) -> CatalogModelsOut:
    """Call the provider /models endpoint (or models.dev for catalog) before save."""
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


async def _refresh_provider_models(
    db: DB, org: Organization, provider_id: str
) -> CatalogModelsOut:
    """Re-fetch models and persist ids onto models_allowlist."""
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


async def _test_provider(
    db: DB, org: Organization, provider_id: str
) -> ProviderTestOut:
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


async def _set_default(
    db: DB, org: Organization, provider_id: str, body: SetDefaultRequest
) -> SetDefaultOut:
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


def _system_hub_out(org: Organization) -> SystemHubOut:
    return SystemHubOut(
        provider_id=org.system_hub_provider_id,
        model=org.system_hub_model,
        configured=bool(org.system_hub_provider_id and org.system_hub_model),
    )


async def _update_system_hub(
    db: DB, org: Organization, body: SystemHubUpdate
) -> SystemHubOut:
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
    return _system_hub_out(org)


def _cerebellum_defaults_out(org: Organization) -> CerebellumDefaultsOut:
    return CerebellumDefaultsOut(
        provider_id=org.cerebellum_default_provider_id,
        model=org.cerebellum_default_model,
    )


async def _update_cerebellum_defaults(
    db: DB, org: Organization, body: CerebellumDefaultsUpdate
) -> CerebellumDefaultsOut:
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
    return _cerebellum_defaults_out(org)


# default-org aliases (legacy; super-admin gated on writes)


@router.get("/default/providers", response_model=list[OrganizationProviderOut])
async def list_providers(
    db: DB,
    current_user: CurrentUserDep,
    enabled: bool | None = Query(default=None),
) -> list[OrganizationProvider]:
    org = await _get_default_org(db)
    return await _list_providers(db, org, enabled)


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
    return await _create_provider(db, org, body)


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
    return await _update_provider(db, org, provider_id, body)


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
    await _delete_provider(db, org, provider_id)
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
    return await _preview_provider_models(db, body)


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
    return await _refresh_provider_models(db, org, provider_id)


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
    return await _test_provider(db, org, provider_id)


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
    return await _set_default(db, org, provider_id, body)


@router.get("/default/system-hub", response_model=SystemHubOut)
async def get_system_hub(
    db: DB,
    current_user: CurrentUserDep,
) -> SystemHubOut:
    org = await _get_default_org(db)
    return _system_hub_out(org)


@router.patch("/default/system-hub", response_model=SystemHubOut)
async def update_system_hub(
    body: SystemHubUpdate,
    db: DB,
    current_user: CurrentUserDep,
) -> SystemHubOut:
    require_super_admin(current_user)
    org = await _get_default_org(db)
    return await _update_system_hub(db, org, body)


@router.get("/default/cerebellum-defaults", response_model=CerebellumDefaultsOut)
async def get_cerebellum_defaults(
    db: DB,
    current_user: CurrentUserDep,
) -> CerebellumDefaultsOut:
    org = await _get_default_org(db)
    return _cerebellum_defaults_out(org)


@router.patch("/default/cerebellum-defaults", response_model=CerebellumDefaultsOut)
async def update_cerebellum_defaults(
    body: CerebellumDefaultsUpdate,
    db: DB,
    current_user: CurrentUserDep,
) -> CerebellumDefaultsOut:
    require_super_admin(current_user)
    org = await _get_default_org(db)
    return await _update_cerebellum_defaults(db, org, body)


# org-scoped twins: reads = membership; writes = can_manage_organization


@router.get("/{org_id}/providers", response_model=list[OrganizationProviderOut])
async def list_org_providers(
    org_id: str,
    db: DB,
    current_user: CurrentUserDep,
    enabled: bool | None = Query(default=None),
) -> list[OrganizationProvider]:
    org = await _get_org_for_user(db, current_user, org_id)
    return await _list_providers(db, org, enabled)


@router.post(
    "/{org_id}/providers",
    response_model=OrganizationProviderOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_org_provider(
    org_id: str,
    body: OrganizationProviderCreate,
    db: DB,
    current_user: CurrentUserDep,
) -> OrganizationProvider:
    org = await _get_org_for_user(db, current_user, org_id)
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_organization",
        organization_id=org.id,
    )
    return await _create_provider(db, org, body)


@router.get(
    "/{org_id}/providers/{provider_id}",
    response_model=OrganizationProviderOut,
)
async def get_org_provider(
    org_id: str,
    provider_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> OrganizationProvider:
    org = await _get_org_for_user(db, current_user, org_id)
    return await _get_provider(db, org.id, provider_id)


@router.patch(
    "/{org_id}/providers/{provider_id}",
    response_model=OrganizationProviderOut,
)
async def update_org_provider(
    org_id: str,
    provider_id: str,
    body: OrganizationProviderUpdate,
    db: DB,
    current_user: CurrentUserDep,
) -> OrganizationProvider:
    org = await _get_org_for_user(db, current_user, org_id)
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_organization",
        organization_id=org.id,
    )
    return await _update_provider(db, org, provider_id, body)


@router.delete(
    "/{org_id}/providers/{provider_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_org_provider(
    org_id: str,
    provider_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> Response:
    org = await _get_org_for_user(db, current_user, org_id)
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_organization",
        organization_id=org.id,
    )
    await _delete_provider(db, org, provider_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{org_id}/providers/preview-models",
    response_model=CatalogModelsOut,
)
async def preview_org_provider_models(
    org_id: str,
    body: PreviewModelsRequest,
    db: DB,
    current_user: CurrentUserDep,
) -> CatalogModelsOut:
    """Call the provider /models endpoint (or models.dev for catalog) before save."""
    org = await _get_org_for_user(db, current_user, org_id)
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_organization",
        organization_id=org.id,
    )
    return await _preview_provider_models(db, body)


@router.post(
    "/{org_id}/providers/{provider_id}/refresh-models",
    response_model=CatalogModelsOut,
)
async def refresh_org_provider_models(
    org_id: str,
    provider_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> CatalogModelsOut:
    """Re-fetch models and persist ids onto models_allowlist."""
    org = await _get_org_for_user(db, current_user, org_id)
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_organization",
        organization_id=org.id,
    )
    return await _refresh_provider_models(db, org, provider_id)


@router.post(
    "/{org_id}/providers/{provider_id}/test",
    response_model=ProviderTestOut,
)
async def test_org_provider(
    org_id: str,
    provider_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> ProviderTestOut:
    org = await _get_org_for_user(db, current_user, org_id)
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_organization",
        organization_id=org.id,
    )
    return await _test_provider(db, org, provider_id)


@router.post(
    "/{org_id}/providers/{provider_id}/set-default",
    response_model=SetDefaultOut,
)
async def set_org_provider_default(
    org_id: str,
    provider_id: str,
    body: SetDefaultRequest,
    db: DB,
    current_user: CurrentUserDep,
) -> SetDefaultOut:
    org = await _get_org_for_user(db, current_user, org_id)
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_organization",
        organization_id=org.id,
    )
    return await _set_default(db, org, provider_id, body)


@router.get("/{org_id}/system-hub", response_model=SystemHubOut)
async def get_org_system_hub(
    org_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> SystemHubOut:
    org = await _get_org_for_user(db, current_user, org_id)
    return _system_hub_out(org)


@router.patch("/{org_id}/system-hub", response_model=SystemHubOut)
async def update_org_system_hub(
    org_id: str,
    body: SystemHubUpdate,
    db: DB,
    current_user: CurrentUserDep,
) -> SystemHubOut:
    org = await _get_org_for_user(db, current_user, org_id)
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_organization",
        organization_id=org.id,
    )
    return await _update_system_hub(db, org, body)


@router.get("/{org_id}/cerebellum-defaults", response_model=CerebellumDefaultsOut)
async def get_org_cerebellum_defaults(
    org_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> CerebellumDefaultsOut:
    org = await _get_org_for_user(db, current_user, org_id)
    return _cerebellum_defaults_out(org)


@router.patch("/{org_id}/cerebellum-defaults", response_model=CerebellumDefaultsOut)
async def update_org_cerebellum_defaults(
    org_id: str,
    body: CerebellumDefaultsUpdate,
    db: DB,
    current_user: CurrentUserDep,
) -> CerebellumDefaultsOut:
    org = await _get_org_for_user(db, current_user, org_id)
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_organization",
        organization_id=org.id,
    )
    return await _update_cerebellum_defaults(db, org, body)


def _org_out(org: Organization) -> OrganizationOut:
    """Serialize an Organization ORM row to the wire schema (id included)."""
    return OrganizationOut.model_validate(org)


async def _get_org_for_user(
    db: DB, current_user: CurrentUserDep, org_id: str
) -> Organization:
    """Fetch an org by id; 404 when missing/deleted or the caller is not a
    member (super-admin bypasses). Non-members get 404, not 403, so org
    existence is not leaked (permission_bypass adversarial class).

    Design §3.6: a contract whose effective atom set is empty is treated as
    "no access" — the caller is not a member for org-level access.
    """
    org = await db.get(Organization, org_id)
    if org is None or org.deleted_at is not None:
        raise NotFoundError(
            "organization.not_found",
            "errors.organization.not_found",
            f"Organization '{org_id}' not found",
        )
    if current_user.is_super_admin:
        return org
    result = await db.execute(
        select(OrganizationContract.id).where(
            OrganizationContract.organization_id == org.id,
            OrganizationContract.user_id == current_user.user_id,
            OrganizationContract.deleted_at.is_(None),
        )
    )
    if result.scalar_one_or_none() is None:
        raise NotFoundError(
            "organization.not_found",
            "errors.organization.not_found",
            f"Organization '{org_id}' not found",
        )
    has_atom = await db.execute(
        select(OrganizationContractGene.id)
        .join(
            OrganizationContract,
            OrganizationContract.id == OrganizationContractGene.contract_id,
        )
        .where(
            OrganizationContract.organization_id == org.id,
            OrganizationContract.user_id == current_user.user_id,
            OrganizationContract.deleted_at.is_(None),
            OrganizationContractGene.deleted_at.is_(None),
        )
        .limit(1)
    )
    if has_atom.scalar_one_or_none() is None:
        raise NotFoundError(
            "organization.not_found",
            "errors.organization.not_found",
            f"Organization '{org_id}' not found",
        )
    return org


@router.get("", response_model=OffsetPage[OrganizationOut])
async def list_organizations(
    db: DB,
    current_user: CurrentUserDep,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> OffsetPage:
    """List orgs the caller holds at least one valid OrganizationContract in.

    Powers the v4-3 OrgPicker. Sorted by creation order (oldest first).
    Design §3.6: a contract with zero active gene atoms is not "valid" — the
    org is excluded from the picker for that user.
    """
    stmt = (
        select(Organization)
        .join(
            OrganizationContract,
            OrganizationContract.organization_id == Organization.id,
        )
        .where(
            OrganizationContract.user_id == current_user.user_id,
            OrganizationContract.deleted_at.is_(None),
            Organization.deleted_at.is_(None),
            exists(
                select(OrganizationContractGene.id).where(
                    OrganizationContractGene.contract_id
                    == OrganizationContract.id,
                    OrganizationContractGene.deleted_at.is_(None),
                )
            ),
        )
        .order_by(Organization.created_at)
    )
    page = await paginate_offset(db, stmt, offset, min(limit, 200))
    items = [_org_out(o) for o in page.items]
    return OffsetPage(
        items=items,
        offset=page.offset,
        limit=page.limit,
        total=page.total,
    )


@router.get("/{org_id}", response_model=OrganizationOut)
async def get_organization(
    org_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> Organization:
    """Return one org by id; 404 when not a member (or org missing)."""
    return await _get_org_for_user(db, current_user, org_id)


@router.patch("/{org_id}", response_model=OrganizationOut)
async def update_organization(
    org_id: str,
    body: OrganizationUpdate,
    db: DB,
    current_user: CurrentUserDep,
) -> Organization:
    """Update org settings (name/description/system-hub/cerebellum/proxy).

    Requires ``can_manage_organization`` on the org (super-admin bypasses).
    """
    org = await _get_org_for_user(db, current_user, org_id)
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_organization",
        organization_id=org.id,
    )
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(org, field, value)
    await db.commit()
    await db.refresh(org)
    return org


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization(
    org_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> Response:
    """Soft-delete an org and cascade through its tenant hierarchy (M6/M5).

    Requires ``can_manage_organization`` (super-admin bypasses). All rows are
    soft-deleted via ``BaseModel.soft_delete()`` — never ``db.delete()``.
    Best-effort pod deletion is intentionally a no-op stub in this wave.
    """
    org = await _get_org_for_user(db, current_user, org_id)
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_organization",
        organization_id=org.id,
    )

    contract_rows = (
        await db.execute(
            select(OrganizationContract).where(
                OrganizationContract.organization_id == org.id,
                OrganizationContract.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    contract_ids = [c.id for c in contract_rows]
    if contract_ids:
        genes = (
            await db.execute(
                select(OrganizationContractGene).where(
                    OrganizationContractGene.contract_id.in_(contract_ids),
                    OrganizationContractGene.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        for gene in genes:
            gene.soft_delete()

    ns_rows = (
        await db.execute(
            select(Namespace).where(
                Namespace.org_id == org.id,
                Namespace.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    ns_ids = [ns.id for ns in ns_rows]

    ns_contract_rows = []
    ns_contract_ids: list[str] = []
    if ns_ids:
        ns_contract_rows = (
            await db.execute(
                select(NamespaceContract).where(
                    NamespaceContract.namespace_id.in_(ns_ids),
                    NamespaceContract.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        ns_contract_ids = [c.id for c in ns_contract_rows]
    if ns_contract_ids:
        ns_genes = (
            await db.execute(
                select(NamespaceContractGene).where(
                    NamespaceContractGene.contract_id.in_(ns_contract_ids),
                    NamespaceContractGene.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        for gene in ns_genes:
            gene.soft_delete()

    ws_rows = []
    ws_ids: list[str] = []
    if ns_ids:
        ws_rows = (
            await db.execute(
                select(Workspace).where(
                    Workspace.namespace_id.in_(ns_ids),
                    Workspace.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        ws_ids = [ws.id for ws in ws_rows]

    entity_rows = []
    entity_ids: list[str] = []
    if ns_ids:
        entity_rows = (
            await db.execute(
                select(Entity).where(
                    Entity.namespace_id.in_(ns_ids),
                    Entity.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        entity_ids = [e.id for e in entity_rows]
    if entity_ids:
        caps = (
            await db.execute(
                select(EntityCapability).where(
                    EntityCapability.entity_id.in_(entity_ids),
                    EntityCapability.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        for cap in caps:
            cap.soft_delete()
        ai_genes = (
            await db.execute(
                select(EntityAiGene).where(
                    EntityAiGene.entity_id.in_(entity_ids),
                    EntityAiGene.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        for link in ai_genes:
            link.soft_delete()

    if ws_ids:
        memberships = (
            await db.execute(
                select(Membership).where(
                    Membership.workspace_id.in_(ws_ids),
                    Membership.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        for mem in memberships:
            mem.soft_delete()
        passages = (
            await db.execute(
                select(Passage).where(
                    Passage.workspace_id.in_(ws_ids),
                    Passage.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        for passage in passages:
            passage.soft_delete()
        instances = (
            await db.execute(
                select(Instance).where(
                    Instance.workspace_id.in_(ws_ids),
                    Instance.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        for inst in instances:
            inst.soft_delete()

    providers = (
        await db.execute(
            select(OrganizationProvider).where(
                OrganizationProvider.organization_id == org.id,
                OrganizationProvider.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    provider_ids = [p.id for p in providers]
    if provider_ids:
        provider_defaults = (
            await db.execute(
                select(BaseClassProviderDefault).where(
                    BaseClassProviderDefault.provider_id.in_(provider_ids),
                    BaseClassProviderDefault.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        for row in provider_defaults:
            row.soft_delete()
    for provider in providers:
        provider.soft_delete()

    knowledge_entries = (
        await db.execute(
            select(KnowledgeEntry).where(
                KnowledgeEntry.organization_id == org.id,
                KnowledgeEntry.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    for row in knowledge_entries:
        row.soft_delete()
    knowledge_dimensions = (
        await db.execute(
            select(KnowledgeDimension).where(
                KnowledgeDimension.organization_id == org.id,
                KnowledgeDimension.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    for row in knowledge_dimensions:
        row.soft_delete()

    for ws in ws_rows:
        ws.soft_delete()
    for entity in entity_rows:
        entity.soft_delete()
    for ns in ns_rows:
        ns.soft_delete()
    for ns_contract in ns_contract_rows:
        ns_contract.soft_delete()
    for contract in contract_rows:
        contract.soft_delete()

    org.soft_delete()
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _atom_genes(db: DB, slugs: list[str]) -> dict[str, UserGene]:
    """Validate slugs against ``ATOM_CATALOG`` and return slug → gene row.

    Unknown slugs → 422 ``user_gene.not_found`` (malformed input class).
    """
    if not slugs:
        return {}
    unknown = sorted(set(slugs) - set(ATOM_CATALOG))
    if unknown:
        raise ValidationError(
            "user_gene.not_found",
            "errors.user_gene.not_found",
            f"Unknown atom gene slug(s): {', '.join(unknown)}",
        )
    await ensure_atom_genes(db)
    rows = (
        await db.execute(
            select(UserGene).where(
                UserGene.slug.in_(set(slugs)),
                UserGene.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    return {g.slug: g for g in rows}


async def _resolve_unique_user(db: DB, q: str) -> User:
    """Resolve a user by unique username/email prefix (``q``).

    Mirrors the ``GET /users/search`` ILIKE-prefix semantics (wildcards
    escaped and treated literally). Zero matches → 404; multiple → 422
    ``organization.member_ambiguous``.
    """
    needle = q.strip()
    escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"{escaped}%"
    rows = (
        await db.execute(
            select(User)
            .where(
                User.deleted_at.is_(None),
                or_(
                    User.username.ilike(pattern, escape="\\"),
                    User.email.ilike(pattern, escape="\\"),
                ),
            )
            .order_by(User.username, User.id)
            .limit(2)
        )
    ).scalars().all()
    if not rows:
        raise NotFoundError(
            "user.not_found",
            "errors.user.not_found",
            f"No user matches '{q}'",
        )
    if len(rows) > 1:
        raise ValidationError(
            "organization.member_ambiguous",
            "errors.organization.member_ambiguous",
            f"'{q}' matches more than one user — provide a more specific prefix",
        )
    return rows[0]


async def _get_org_contract(
    db: DB, org_id: str, contract_id: str
) -> OrganizationContract:
    """Fetch an active OrganizationContract scoped to the org; 404 otherwise."""
    contract = await db.get(OrganizationContract, contract_id)
    if (
        contract is None
        or contract.deleted_at is not None
        or contract.organization_id != org_id
    ):
        raise NotFoundError(
            "organization_contract.not_found",
            "errors.organization_contract.not_found",
            f"OrganizationContract '{contract_id}' not found",
        )
    return contract


async def _org_member_item(
    db: DB, contract: OrganizationContract
) -> dict | None:
    """Serialize one contract to the locked D14 member item (nested user).

    Returns None only when the FK-backed user row is missing — the list
    caller skips such stale contracts instead of failing the whole page.
    """
    user = await db.get(User, contract.user_id)
    if user is None:
        return None
    atoms = (
        await db.execute(
            select(UserGene)
            .join(
                OrganizationContractGene,
                OrganizationContractGene.user_gene_id == UserGene.id,
            )
            .where(
                OrganizationContractGene.contract_id == contract.id,
                OrganizationContractGene.deleted_at.is_(None),
                UserGene.deleted_at.is_(None),
            )
            .order_by(UserGene.slug)
        )
    ).scalars().all()
    return {
        "id": contract.id,
        "user": OrganizationMemberUserRef(
            id=user.id,
            username=user.username,
            email=user.email,
            nickname=user.nickname,
        ),
        "atoms": [
            OrganizationMemberAtomRef(id=g.id, slug=g.slug, name=g.name)
            for g in atoms
        ],
        "created_at": contract.created_at,
    }


async def _contract_slugs(db: DB, contract_id: str) -> set[str]:
    """Active atom slugs of one contract (used by the H5 self-lock guard)."""
    rows = (
        await db.execute(
            select(UserGene.slug)
            .join(
                OrganizationContractGene,
                OrganizationContractGene.user_gene_id == UserGene.id,
            )
            .where(
                OrganizationContractGene.contract_id == contract_id,
                OrganizationContractGene.deleted_at.is_(None),
                UserGene.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    return set(rows)


def _raise_cannot_lock_self() -> NoReturn:
    """H5 防自锁 — 400 errors.org.cannot_lock_self (locked pair)."""
    raise CocoaError(
        "errors.org.cannot_lock_self",
        "organization.cannot_lock_self",
        "Cannot strip your own last can_manage_org_members grant",
        status_code=400,
    )


async def _org_has_other_manage_holder(
    db: DB, org_id: str, contract_id: str
) -> bool:
    """True when another active contract in the org holds a manage atom.

    Manage atoms are ``can_manage_organization`` / ``can_manage_org_members``
    — the two atoms whose loss would lock the org out of self-management.
    """
    rows = (
        await db.execute(
            select(OrganizationContractGene.contract_id)
            .select_from(OrganizationContractGene)
            .join(
                OrganizationContract,
                OrganizationContract.id == OrganizationContractGene.contract_id,
            )
            .join(UserGene, UserGene.id == OrganizationContractGene.user_gene_id)
            .where(
                OrganizationContract.organization_id == org_id,
                OrganizationContractGene.contract_id != contract_id,
                OrganizationContract.deleted_at.is_(None),
                OrganizationContractGene.deleted_at.is_(None),
                UserGene.deleted_at.is_(None),
                UserGene.slug.in_(
                    ("can_manage_organization", "can_manage_org_members")
                ),
            )
            .limit(1)
        )
    ).scalars().all()
    return len(rows) > 0


async def _guard_cannot_lock_self(
    db: DB,
    current_user: CurrentUserDep,
    org_id: str,
    contract: OrganizationContract,
    *,
    desired_slugs: set[str] | None,
    deleting: bool,
) -> None:
    """H5 防自锁 guard on PATCH/DELETE of a member contract.

    Locked semantics: 不可剥自己最后一枚 manage_members（PATCH 自剥 → 400）；
    删除/自改后 org 若不再有任何 contract 持有
    ``can_manage_organization`` / ``can_manage_org_members`` → 400
    （v4.3 review: zero-atom 成员可被利用制造永久无管理人 org）。Super-admins
    bypass.
    """
    if current_user.is_super_admin:
        return
    if contract.user_id != current_user.user_id:
        return
    if deleting:
        if not await _org_has_other_manage_holder(db, org_id, contract.id):
            _raise_cannot_lock_self()
        return
    current = await _contract_slugs(db, contract.id)
    desired = desired_slugs or set()
    if "can_manage_org_members" in current and "can_manage_org_members" not in desired:
        _raise_cannot_lock_self()
    post_change_holds_manage = bool({"can_manage_organization", "can_manage_org_members"} & desired)
    if not post_change_holds_manage and not await _org_has_other_manage_holder(
        db, org_id, contract.id
    ):
        _raise_cannot_lock_self()


@router.get("/{org_id}/members", response_model=OffsetPage[OrganizationMemberOut])
async def list_org_members(
    org_id: str,
    db: DB,
    current_user: CurrentUserDep,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> OffsetPage:
    """List the org's world contracts (世界契印) with nested user + atoms.

    Permission (weaker of the two): the caller must hold
    ``can_view_workspace`` OR ``can_manage_org_members`` on the org.
    Non-members get 404 (no existence leak), like the org CRUD lanes.
    """
    org = await _get_org_for_user(db, current_user, org_id)
    if not current_user.is_super_admin:
        slugs = await list_grant_slugs(
            db, current_user.user_id, organization_id=org.id
        )
        if not ({"can_view_workspace", "can_manage_org_members"} & slugs):
            raise ForbiddenError(
                "permission.denied",
                "errors.permission.denied",
                f"User '{current_user.user_id}' lacks permission to view members",
                details={
                    "user_id": current_user.user_id,
                    "permission_key": "can_view_workspace|can_manage_org_members",
                    "organization_id": org.id,
                },
            )

    stmt = (
        select(OrganizationContract)
        .where(
            OrganizationContract.organization_id == org.id,
            OrganizationContract.deleted_at.is_(None),
        )
        .order_by(OrganizationContract.created_at)
    )
    page = await paginate_offset(db, stmt, offset, min(limit, 200))
    items: list[dict] = []
    for contract in page.items:
        item = await _org_member_item(db, contract)
        if item is not None:
            items.append(item)
    return OffsetPage(
        items=items,
        offset=page.offset,
        limit=page.limit,
        total=page.total,
    )


@router.post(
    "/{org_id}/members",
    response_model=OrganizationMemberOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_org_member(
    org_id: str,
    body: OrganizationMemberCreate,
    db: DB,
    current_user: CurrentUserDep,
) -> dict:
    """Add a member to the world — by ``user_id`` or unique-prefix ``q``.

    Requires ``can_manage_org_members`` on the org. Returns the D14 member
    item (same shape as GET list items).
    """
    org = await _get_org_for_user(db, current_user, org_id)
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_org_members",
        organization_id=org.id,
    )

    if body.user_id is not None:
        user = await db.get(User, body.user_id)
        if user is None or user.deleted_at is not None:
            raise NotFoundError(
                "user.not_found",
                "errors.user.not_found",
                f"User '{body.user_id}' not found",
            )
    else:
        user = await _resolve_unique_user(db, body.q or "")

    existing = await db.execute(
        select(OrganizationContract).where(
            OrganizationContract.organization_id == org.id,
            OrganizationContract.user_id == user.id,
            OrganizationContract.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(
            "organization.member_exists",
            "errors.organization.member_exists",
            f"User '{user.username}' is already a member of this organization",
        )

    await _atom_genes(db, body.atom_slugs)  # validate slugs (422 on unknown)
    username = user.username  # materialized before rollback expires the row
    try:
        contract = await ensure_org_contract(
            db, organization_id=org.id, user_id=user.id
        )
        await grant_atoms(db, contract.id, body.atom_slugs)
        await db.commit()
    except IntegrityError:
        # Race: a concurrent request inserted the same (org, user) contract
        # after our pre-check and the partial unique index fired. Map to the
        # same 409 as the sequential duplicate path.
        await db.rollback()
        raise ConflictError(
            "organization.member_exists",
            "errors.organization.member_exists",
            f"User '{username}' is already a member of this organization",
        ) from None
    await db.refresh(contract)
    item = await _org_member_item(db, contract)
    if item is None:
        raise NotFoundError(
            "user.not_found",
            "errors.user.not_found",
            f"User '{user.id}' not found",
        )
    return item


@router.patch(
    "/{org_id}/members/{contract_id}",
    response_model=OrganizationMemberOut,
)
async def update_org_member_atoms(
    org_id: str,
    contract_id: str,
    body: OrganizationMemberAtomsUpdate,
    db: DB,
    current_user: CurrentUserDep,
) -> dict:
    """Replace a member's atom set (old links soft-deleted, new ones added).

    H5: stripping the caller's own ``can_manage_org_members`` → 400
    ``errors.org.cannot_lock_self`` (super-admin bypasses).
    """
    org = await _get_org_for_user(db, current_user, org_id)
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_org_members",
        organization_id=org.id,
    )
    contract = await _get_org_contract(db, org.id, contract_id)
    genes_by_slug = await _atom_genes(db, body.atom_slugs)

    await _guard_cannot_lock_self(
        db,
        current_user,
        org.id,
        contract,
        desired_slugs=set(body.atom_slugs),
        deleting=False,
    )

    links = (
        await db.execute(
            select(OrganizationContractGene).where(
                OrganizationContractGene.contract_id == contract.id,
                OrganizationContractGene.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    desired_ids = {g.id for g in genes_by_slug.values()}
    current_ids = {link.user_gene_id for link in links}
    for link in links:
        if link.user_gene_id not in desired_ids:
            link.soft_delete()
    for gene_id in desired_ids - current_ids:
        db.add(OrganizationContractGene(contract_id=contract.id, user_gene_id=gene_id))
    await db.commit()
    await db.refresh(contract)
    item = await _org_member_item(db, contract)
    if item is None:
        raise NotFoundError(
            "user.not_found",
            "errors.user.not_found",
            f"User '{contract.user_id}' not found",
        )
    return item


@router.delete(
    "/{org_id}/members/{contract_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_org_member(
    org_id: str,
    contract_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> Response:
    """Soft-delete a member's world contract + its atom genes.

    H5: an org with a single contract (org 仅一人) cannot DELETE its own
    contract → 400 ``errors.org.cannot_lock_self`` (super-admin bypasses).
    """
    org = await _get_org_for_user(db, current_user, org_id)
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_org_members",
        organization_id=org.id,
    )
    contract = await _get_org_contract(db, org.id, contract_id)

    await _guard_cannot_lock_self(
        db,
        current_user,
        org.id,
        contract,
        desired_slugs=None,
        deleting=True,
    )

    genes = (
        await db.execute(
            select(OrganizationContractGene).where(
                OrganizationContractGene.contract_id == contract.id,
                OrganizationContractGene.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    for gene in genes:
        gene.soft_delete()
    contract.soft_delete()
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
