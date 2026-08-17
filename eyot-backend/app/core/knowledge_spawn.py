"""Spawn-time knowledge injection + self-consistency hint (v4.9.3, Worker C).

Two dual-dimension concepts (design lock §B1b):

- **has knowledge** — slugs stored on BaseClass / Entity (real assets); at
  spawn they are resolved through the scope-chain rules and injected into
  ``runtime_config["knowledge"] = {"env": {slug: body}, "files": []}``.
- **required knowledge** — slugs declared by the entity's capabilities and
  genes. The spawn-time consistency check is NON-blocking (Q4): when
  ``has ⊉ required`` callers attach ``{"missing": [...]}`` to the response
  and emit an audit event, but the spawn always succeeds.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.knowledge import resolve_knowledge_winners
from app.models.entity import Entity


async def compute_has_knowledge(db: AsyncSession, entity: Entity) -> set[str]:
    """Union of has-knowledge slugs for an entity: BaseClass ∪ Entity.

    Reads ``entities.has_knowledge`` plus ``base_classes.has_knowledge`` for
    the BaseClass referenced by ``entity.preset_slug`` (inheritance direction
    神职 → 眷族). Returns an empty set when nothing is declared.
    """
    from app.models.base_class import BaseClass

    has = set(entity.has_knowledge or [])
    if entity.preset_slug:
        result = await db.execute(
            select(BaseClass).where(
                BaseClass.slug == entity.preset_slug,
                BaseClass.deleted_at.is_(None),
            )
        )
        base_class = result.scalar_one_or_none()
        if base_class is not None:
            has.update(base_class.has_knowledge or [])
    return has


async def compute_required_knowledge(db: AsyncSession, entity: Entity) -> set[str]:
    """Union of required-knowledge slugs declared by an entity's surface.

    Sources (design lock §B1b): market capabilities attached via the
    ``entity_capabilities`` junction, plus every gene attached to the entity
    (explicit ``entity_ai_genes`` rows and genes inherited from the BaseClass)
    — each gene contributes its manifest ``required_knowledge``, any
    inline-capability ``required_knowledge``, and the ``required_knowledge``
    of the ``capability_market`` rows its inline capabilities reference by
    name (运行时展开, design lock §设计锁定).
    """
    from app.core.capabilities import load_entity_ai_gene_dicts
    from app.models.ai_gene import AiGene
    from app.models.capability_market import CapabilityMarketEntry
    from app.models.junctions import EntityCapability

    required: set[str] = set()

    result = await db.execute(
        select(CapabilityMarketEntry)
        .join(
            EntityCapability,
            EntityCapability.capability_id == CapabilityMarketEntry.id,
        )
        .where(
            EntityCapability.entity_id == entity.id,
            EntityCapability.deleted_at.is_(None),
            CapabilityMarketEntry.deleted_at.is_(None),
        )
    )
    for cap in result.scalars().all():
        required.update(cap.required_knowledge or [])

    gene_dicts = await load_entity_ai_gene_dicts(db, entity)
    if gene_dicts:
        slugs = [gene["slug"] for gene in gene_dicts]
        genes = await db.execute(
            select(AiGene).where(
                AiGene.slug.in_(slugs),
                AiGene.deleted_at.is_(None),
            )
        )
        inline_names: set[str] = set()
        for gene in genes.scalars().all():
            manifest = gene.manifest or {}
            own = manifest.get("required_knowledge")
            if isinstance(own, list):
                required.update(str(item) for item in own)
            caps = manifest.get("capabilities")
            if isinstance(caps, list):
                for cap in caps:
                    if not isinstance(cap, dict):
                        continue
                    inline = cap.get("required_knowledge")
                    if isinstance(inline, list):
                        required.update(str(item) for item in inline)
                    name = cap.get("name")
                    if isinstance(name, str) and name:
                        inline_names.add(name)
        if inline_names:
            market_rows = await db.execute(
                select(CapabilityMarketEntry).where(
                    CapabilityMarketEntry.name.in_(inline_names),
                    CapabilityMarketEntry.deleted_at.is_(None),
                )
            )
            for market in market_rows.scalars().all():
                required.update(market.required_knowledge or [])
    return required


async def check_knowledge_consistency(
    db: AsyncSession, entity: Entity
) -> dict[str, list[str]] | None:
    """Non-blocking spawn hint (v4.9.3 Q4): ``{"missing": [...]}`` or ``None``.

    ``missing = required - has``. A non-``None`` result NEVER blocks the
    spawn — callers attach it as a warning and emit an audit event.
    """
    required = await compute_required_knowledge(db, entity)
    has = await compute_has_knowledge(db, entity)
    missing = sorted(required - has)
    if not missing:
        return None
    return {"missing": missing}


async def build_spawn_knowledge_payload(
    db: AsyncSession,
    *,
    entity: Entity,
    workspace_id: str | None,
) -> dict[str, Any] | None:
    """Build ``runtime_config["knowledge"]`` for a spawning instance.

    has-slugs = :func:`compute_has_knowledge` (BaseClass ∪ Entity); each slug
    is looked up in ``knowledge_entries`` through the scope-chain rules
    (workspace > namespace > org > system, unbound rows only — the instance
    is not persisted yet). Returns ``None`` when there is nothing to inject
    (no has slugs, or none of them resolves to an entry), so callers can
    omit the key and leave ``runtime_config.agent_config`` untouched.
    """
    has = await compute_has_knowledge(db, entity)
    if not has:
        return None
    entries = await resolve_knowledge_winners(
        db,
        entity_id=entity.id,
        workspace_id=workspace_id,
        keys=has,
    )
    env: dict[str, str] = {}
    for entry in entries:
        if entry.key in has:
            env[entry.key] = entry.body
    if not env:
        return None
    return {"env": dict(sorted(env.items())), "files": []}
