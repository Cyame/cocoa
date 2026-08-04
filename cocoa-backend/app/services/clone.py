"""Deep-copy clone operations for BaseClass, Entity, Organization, Workspace (v4.4).

Semantics (see .omo/plans/v4-4-clone-ops.md):
- BaseClass / Entity: copy fields + NEW junction rows (never share junction ids).
- Organization: copy NS/WS structure + org-owned BCs; ZERO Contract copy;
  only caller gets OrgContract + ORG_OWNER_ATOMS; no Instances.
- Workspace: awakened induced subgraph (user memberships + passages where
  both endpoints are awakened); lost instance seats omitted; passages touching
  lost endpoints dropped with workspace.clone_passage_dropped event.
- Instance: no clone endpoint (permanently closed).
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
from app.models.workspace import Membership, Passage, Workspace

_LARGE_ORG_THRESHOLD = 5000
_LARGE_ORG_TIMEOUT = "60s"


def _new_slug(source_slug: str, override: str | None) -> str:
    if override is not None:
        return override
    return f"{source_slug}-clone-{uuid.uuid4().hex[:8]}"


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
                           name: str | None = None, slug: str | None = None) -> BaseClass:
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
    new_bc = BaseClass(slug=new_slug, name=_new_name(source.name, name),
                      display_name=source.display_name, description=source.description,
                      manifest=source.manifest, scope=source.scope,
                      organization_id=source.organization_id, namespace_id=source.namespace_id,
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
                           proxy_username=source.proxy_username, proxy_password=source.proxy_password)
    db.add(new_org)
    await db.flush()

    ns_map: dict[str, Namespace] = {}
    for ns in source_ns:
        new_ns = Namespace(org_id=new_org.id, slug=ns.slug, name=ns.name,
                           description=ns.description, tags=ns.tags)
        db.add(new_ns)
        await db.flush()
        ns_map[ns.id] = new_ns

    for ws in source_ws:
        db.add(Workspace(namespace_id=ns_map[ws.namespace_id].id, slug=ws.slug, name=ws.name))
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
        new_ns_id = ns_map[bc.namespace_id].id if bc.namespace_id else None
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
