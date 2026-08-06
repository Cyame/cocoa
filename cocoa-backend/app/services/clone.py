"""Deep-copy clone operations for BaseClass, Entity, Organization, Workspace (v4.4).

Semantics (see .omo/plans/v4-4-clone-ops.md):
- BaseClass / Entity: copy fields + NEW junction rows (never share junction ids).
- Organization: copy NS/WS structure + org-owned BCs; ZERO Contract copy;
  only caller gets OrgContract + ORG_OWNER_ATOMS; no Instances.
- Workspace: awakened induced subgraph (user memberships + passages where
  both endpoints are awakened); lost instance seats omitted; passages touching
  lost endpoints dropped with workspace.clone_passage_dropped event.
- Instance: no clone endpoint (permanently closed).

Permission scoping (D10, verified 2026-08-04):
- BaseClass / Entity / Organization clone routes derive the authorization
  scope from the SOURCE resource (require_permission with
  source.organization_id / source.namespace_id / path org_id); the
  X-Organization-Id header is accepted on the base-class and workspace routes
  for cross-org context but never overrides the source resource's own
  ancestry. Entity and organization routes omit the header entirely.
- Org clone copies only org-scoped BCs (``scope != "system"``); system BCs are
  global and never cloned. A direct single-BC clone of a system BC is
  downgraded to ``scope="org"`` on the caller's target organization (v4.9.4
  C0) — the copy never inherits the source's system readonly lock. The
  target-org permission gate lives in the route layer.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.core.event_types import (
    BASE_CLASS_CLONED,
    ENTITY_CLONED,
    ORGANIZATION_CLONED,
    WORKSPACE_CLONE_PASSAGE_DROPPED,
    WORKSPACE_CLONED,
)
from app.core.events import emit
from app.core.gene_atoms import ORG_OWNER_ATOMS, ensure_atom_genes
from app.core.org_contract import ensure_org_contract, grant_atoms
from app.models.ai_gene import BaseClassAiGene
from app.models.base_class import BaseClass
from app.models.central_hub import CentralHub, Vault
from app.models.entity import Entity
from app.models.junctions import BaseClassCapability, EntityAiGene, EntityCapability
from app.models.organization import Namespace, Organization
from app.models.organization_provider import OrganizationProvider
from app.models.workspace import Membership, Passage, Workspace

_LARGE_ORG_THRESHOLD = 5000
_LARGE_ORG_TIMEOUT = "60s"

# All clone target slug columns are String(255). ``-clone-`` + 8 hex chars
# is a fixed 15-char suffix; the source part is truncated so a generated slug
# never overflows the column (overflow would surface as a raw DB error instead
# of the intended slug-taken ConflictError).
_SLUG_MAX = 255


def _new_slug(source_slug: str, override: str | None) -> str:
    if override is not None:
        return override
    suffix = f"-clone-{uuid.uuid4().hex[:8]}"
    return f"{source_slug[: _SLUG_MAX - len(suffix)]}{suffix}"


def _new_name(source_name: str, override: str | None) -> str:
    return override if override is not None else source_name


async def _clone_junction(db, model, *, parent_col, source_parent_id, new_parent_id, ref_col):
    rows = (await db.execute(select(model).where(
        getattr(model, parent_col) == source_parent_id, model.deleted_at.is_(None)
    ))).scalars().all()
    for row in rows:
        db.add(model(**{parent_col: new_parent_id, ref_col: getattr(row, ref_col)}))
    await db.flush()


async def _emit_clone(db, event_type, resource_type, new_id, actor_user_id, source_id):
    await emit(event_type, actor_type="user", actor_id=actor_user_id,
               resource_type=resource_type, resource_id=new_id,
               payload={"actor_user_id": actor_user_id, "source_id": source_id, "new_id": new_id},
               session=db)


async def clone_base_class(db: AsyncSession, *, source_id: str, actor_user_id: str,
                           name: str | None = None, slug: str | None = None,
                           target_org_id: str | None = None) -> BaseClass:
    source = await db.get(BaseClass, source_id)
    if source is None or source.deleted_at is not None:
        raise NotFoundError("base_class.not_found", "errors.base_class.not_found",
                            f"BaseClass '{source_id}' not found")
    new_slug = _new_slug(source.slug, slug)
    clash = await db.execute(select(BaseClass.id).where(
        BaseClass.slug == new_slug, BaseClass.deleted_at.is_(None)))
    if clash.scalar_one_or_none() is not None:
        raise ConflictError("base_class.slug_taken", "errors.base_class.slug_taken",
                            f"BaseClass slug '{new_slug}' is already taken")
    # v4.9.4 C0: cloning a system preset downgrades the copy to org scope on
    # the caller's target organization (a new asset, not an inherited
    # system-only lock). Non-system sources keep source scope/org/ns.
    if source.scope == "system":
        copy_scope, copy_org_id, copy_ns_id = "org", target_org_id, None
    else:
        copy_scope, copy_org_id, copy_ns_id = (
            source.scope, source.organization_id, source.namespace_id
        )
    new_bc = BaseClass(slug=new_slug, name=_new_name(source.name, name),
                      display_name=source.display_name, description=source.description,
                      manifest=source.manifest, scope=copy_scope,
                      organization_id=copy_org_id, namespace_id=copy_ns_id,
                      version=source.version, tags=source.tags)
    db.add(new_bc)
    await db.flush()
    await _clone_junction(db, BaseClassAiGene, parent_col="base_class_id",
                         source_parent_id=source.id, new_parent_id=new_bc.id, ref_col="ai_gene_id")
    await _clone_junction(db, BaseClassCapability, parent_col="base_class_id",
                         source_parent_id=source.id, new_parent_id=new_bc.id, ref_col="capability_id")
    await _emit_clone(db, BASE_CLASS_CLONED, "base_class", new_bc.id, actor_user_id, source_id)
    return new_bc


async def clone_entity(db: AsyncSession, *, source_id: str, actor_user_id: str,
                       name: str | None = None, slug: str | None = None) -> Entity:
    source = await db.get(Entity, source_id)
    if source is None or source.deleted_at is not None:
        raise NotFoundError("entity.not_found", "errors.entity.not_found",
                            f"Entity '{source_id}' not found")
    new_slug = _new_slug(source.slug, slug)
    clash = await db.execute(select(Entity.id).where(
        Entity.namespace_id == source.namespace_id, Entity.slug == new_slug,
        Entity.deleted_at.is_(None)))
    if clash.scalar_one_or_none() is not None:
        raise ConflictError("entity.slug_taken", "errors.entity.slug_taken",
                            f"Entity slug '{new_slug}' is already taken")
    # is_cerebellum is deliberately forced False here: the cerebellum flag is a
    # per-namespace singleton (uq_entities_cerebellum_per_ns), and an entity
    # clone stays in the SOURCE namespace. clone_organization preserves the flag
    # instead, because its entity copies land in fresh (empty) namespaces.
    new_entity = Entity(namespace_id=source.namespace_id, slug=new_slug,
                        name=_new_name(source.name, name), preset_slug=source.preset_slug,
                        rank=source.rank, display_name=source.display_name,
                        display_color=source.display_color, system_prompt=source.system_prompt,
                        config_override=source.config_override, is_cerebellum=False)
    db.add(new_entity)
    await db.flush()
    await _clone_junction(db, EntityAiGene, parent_col="entity_id",
                         source_parent_id=source.id, new_parent_id=new_entity.id, ref_col="ai_gene_id")
    await _clone_junction(db, EntityCapability, parent_col="entity_id",
                         source_parent_id=source.id, new_parent_id=new_entity.id, ref_col="capability_id")
    await _emit_clone(db, ENTITY_CLONED, "entity", new_entity.id, actor_user_id, source_id)
    return new_entity


async def clone_organization(db: AsyncSession, *, source_id: str, actor_user_id: str,
                             name: str | None = None, slug: str | None = None) -> Organization:
    source = await db.get(Organization, source_id)
    if source is None or source.deleted_at is not None:
        raise NotFoundError("organization.not_found", "errors.organization.not_found",
                            f"Organization '{source_id}' not found")
    new_slug = _new_slug(source.slug, slug)
    clash = await db.execute(select(Organization.id).where(
        Organization.slug == new_slug, Organization.deleted_at.is_(None)))
    if clash.scalar_one_or_none() is not None:
        raise ConflictError("organization.slug_taken", "errors.organization.slug_taken",
                            f"Organization slug '{new_slug}' is already taken")

    source_ns = (await db.execute(select(Namespace).where(
        Namespace.org_id == source.id, Namespace.deleted_at.is_(None)))).scalars().all()
    ns_ids = [ns.id for ns in source_ns]
    source_ws, source_entities = [], []
    if ns_ids:
        source_ws = (await db.execute(select(Workspace).where(
            Workspace.namespace_id.in_(ns_ids), Workspace.deleted_at.is_(None)))).scalars().all()
        source_entities = (await db.execute(select(Entity).where(
            Entity.namespace_id.in_(ns_ids), Entity.deleted_at.is_(None)))).scalars().all()
    ws_ids = [ws.id for ws in source_ws]
    if ws_ids:
        mem_count = await db.scalar(select(func.count()).select_from(Membership).where(
            Membership.workspace_id.in_(ws_ids), Membership.deleted_at.is_(None))) or 0
        passage_count = await db.scalar(select(func.count()).select_from(Passage).where(
            Passage.workspace_id.in_(ws_ids), Passage.deleted_at.is_(None))) or 0
        if mem_count + passage_count + len(source_entities) > _LARGE_ORG_THRESHOLD:
            await db.execute(text(f"SET LOCAL statement_timeout = '{_LARGE_ORG_TIMEOUT}'"))

    new_org = Organization(slug=new_slug, name=_new_name(source.name, name),
                           description=source.description, use_proxy=source.use_proxy,
                           proxy_host=source.proxy_host, proxy_port=source.proxy_port,
                           proxy_username=source.proxy_username, proxy_password=source.proxy_password,
                           system_hub_model=source.system_hub_model,
                           cerebellum_default_model=source.cerebellum_default_model)
    db.add(new_org)
    await db.flush()

    # D4: deep-copy the org's LLM provider bindings. The clone gets its OWN
    # provider rows (independent copies, never a shared FK into the source
    # org), and the binding columns point at the copied rows.
    bound_provider_ids = {
        pid for pid in (source.system_hub_provider_id, source.cerebellum_default_provider_id)
        if pid is not None
    }
    provider_id_map: dict[str, str] = {}
    if bound_provider_ids:
        source_providers = (await db.execute(select(OrganizationProvider).where(
            OrganizationProvider.id.in_(bound_provider_ids),
            OrganizationProvider.deleted_at.is_(None)))).scalars().all()
        for prov in source_providers:
            new_prov = OrganizationProvider(
                organization_id=new_org.id, origin=prov.origin,
                catalog_provider_id=prov.catalog_provider_id, name=prov.name, slug=prov.slug,
                request_format=prov.request_format, base_url=prov.base_url,
                api_key_ref=prov.api_key_ref, default_model=prov.default_model,
                models_allowlist=prov.models_allowlist, verify_ssl=prov.verify_ssl,
                models_endpoint_mode=prov.models_endpoint_mode,
                models_base_url=prov.models_base_url, enabled=prov.enabled,
            )
            db.add(new_prov)
            await db.flush()
            provider_id_map[prov.id] = new_prov.id
    if source.system_hub_provider_id in provider_id_map:
        new_org.system_hub_provider_id = provider_id_map[source.system_hub_provider_id]
    if source.cerebellum_default_provider_id in provider_id_map:
        new_org.cerebellum_default_provider_id = provider_id_map[source.cerebellum_default_provider_id]

    ns_map: dict[str, Namespace] = {}
    for ns in source_ns:
        new_ns = Namespace(org_id=new_org.id, slug=ns.slug, name=ns.name,
                           description=ns.description, tags=ns.tags)
        db.add(new_ns)
        await db.flush()
        ns_map[ns.id] = new_ns

    for ws in source_ws:
        new_ws = Workspace(namespace_id=ns_map[ws.namespace_id].id, slug=ws.slug, name=ws.name)
        db.add(new_ws)
        await db.flush()
        # D3: every cloned workspace needs the same 1:1 hub/vault bootstrap
        # that clone_workspace / create_workspace provide, or the portal
        # brain tab renders empty for org-cloned workspaces.
        db.add(CentralHub(workspace_id=new_ws.id))
        db.add(Vault(workspace_id=new_ws.id))
        await db.flush()

    for entity in source_entities:
        ne = Entity(namespace_id=ns_map[entity.namespace_id].id, slug=entity.slug,
                    name=entity.name, preset_slug=entity.preset_slug, rank=entity.rank,
                    display_name=entity.display_name, display_color=entity.display_color,
                    system_prompt=entity.system_prompt, config_override=entity.config_override,
                    is_cerebellum=entity.is_cerebellum)
        db.add(ne)
        await db.flush()
        await _clone_junction(db, EntityAiGene, parent_col="entity_id",
                             source_parent_id=entity.id, new_parent_id=ne.id, ref_col="ai_gene_id")
        await _clone_junction(db, EntityCapability, parent_col="entity_id",
                             source_parent_id=entity.id, new_parent_id=ne.id, ref_col="capability_id")

    source_bcs = (await db.execute(select(BaseClass).where(
        BaseClass.organization_id == source.id, BaseClass.scope != "system",
        BaseClass.deleted_at.is_(None)))).scalars().all()
    for bc in source_bcs:
        # D2: a BC may reference a namespace not in the source org's active
        # set (e.g. soft-deleted); degrade to org-level (None) instead of a
        # raw KeyError -> 500.
        mapped_ns = ns_map.get(bc.namespace_id) if bc.namespace_id else None
        new_ns_id = mapped_ns.id if mapped_ns is not None else None
        nbc = BaseClass(slug=_new_slug(bc.slug, None), name=bc.name,
                        display_name=bc.display_name, description=bc.description,
                        manifest=bc.manifest, scope=bc.scope, organization_id=new_org.id,
                        namespace_id=new_ns_id, version=bc.version, tags=bc.tags)
        db.add(nbc)
        await db.flush()
        await _clone_junction(db, BaseClassAiGene, parent_col="base_class_id",
                             source_parent_id=bc.id, new_parent_id=nbc.id, ref_col="ai_gene_id")
        await _clone_junction(db, BaseClassCapability, parent_col="base_class_id",
                             source_parent_id=bc.id, new_parent_id=nbc.id, ref_col="capability_id")

    await ensure_atom_genes(db)
    contract = await ensure_org_contract(db, organization_id=new_org.id, user_id=actor_user_id)
    await grant_atoms(db, contract.id, ORG_OWNER_ATOMS)
    await _emit_clone(db, ORGANIZATION_CLONED, "organization", new_org.id, actor_user_id, source_id)
    return new_org


async def clone_workspace(db: AsyncSession, *, source_id: str, actor_user_id: str,
                          name: str | None = None, slug: str | None = None) -> Workspace:
    source = await db.get(Workspace, source_id)
    if source is None or source.deleted_at is not None:
        raise NotFoundError("workspace.not_found", "errors.workspace.not_found",
                            f"Workspace '{source_id}' not found")
    new_slug = _new_slug(source.slug, slug)
    clash = await db.execute(select(Workspace.id).where(
        Workspace.namespace_id == source.namespace_id, Workspace.slug == new_slug,
        Workspace.deleted_at.is_(None)))
    if clash.scalar_one_or_none() is not None:
        raise ConflictError("workspace.slug_taken", "errors.workspace.slug_taken",
                            f"Workspace slug '{new_slug}' is already taken")
    new_ws = Workspace(namespace_id=source.namespace_id, slug=new_slug,
                       name=_new_name(source.name, name))
    db.add(new_ws)
    await db.flush()
    db.add(CentralHub(workspace_id=new_ws.id))
    db.add(Vault(workspace_id=new_ws.id))
    await db.flush()

    awakened = (await db.execute(select(Membership).where(
        Membership.workspace_id == source.id, Membership.user_id.is_not(None),
        Membership.deleted_at.is_(None)))).scalars().all()
    mem_map: dict[str, Membership] = {}
    for mem in awakened:
        nm = Membership(workspace_id=new_ws.id, user_id=mem.user_id, posx=mem.posx, posy=mem.posy)
        db.add(nm)
        await db.flush()
        mem_map[mem.id] = nm

    passages = (await db.execute(select(Passage).where(
        Passage.workspace_id == source.id, Passage.deleted_at.is_(None)))).scalars().all()
    for p in passages:
        if p.from_membership_id in mem_map and p.to_membership_id in mem_map:
            nf, nt = mem_map[p.from_membership_id].id, mem_map[p.to_membership_id].id
            if nf > nt:
                nf, nt = nt, nf
            db.add(Passage(workspace_id=new_ws.id, from_membership_id=nf, to_membership_id=nt,
                           is_active=p.is_active, mode=p.mode, edge_meta=p.edge_meta))
        else:
            await emit(WORKSPACE_CLONE_PASSAGE_DROPPED, actor_type="user", actor_id=actor_user_id,
                       resource_type="passage", resource_id=p.id,
                       payload={"source_passage_id": p.id, "reason": "lost_endpoint",
                                "new_workspace_id": new_ws.id}, session=db)
    await db.flush()
    await _emit_clone(db, WORKSPACE_CLONED, "workspace", new_ws.id, actor_user_id, source_id)
    return new_ws
