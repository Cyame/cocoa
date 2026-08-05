"""Capability junction read/write helpers (v4.0).

The write truth for "which capabilities an Entity / BaseClass has" is the
junction tables; API responses still expose aggregated mirror arrays
(``manifest.skills/tools/commands``) for one-generation Portal compatibility.
"""

from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.ai_gene import AiGene, BaseClassAiGene
from app.models.base_class import BaseClass
from app.models.capability_market import CapabilityMarketEntry
from app.models.entity import Entity
from app.models.junctions import (
    BaseClassCapability,
    EntityAiGene,
    EntityCapability,
)

_MIRROR_TYPES = ("skill", "tool", "mcp", "lsp", "command")


def build_capabilities_manifest(entries: Iterable[Any]) -> list[dict[str, Any]]:
    """Serialize capability entries into the manifest inline ``capabilities`` array.

    This is the single shared shape for AiGene manifests (v4.9 A2a): the
    combine endpoint and the ai-genes create/update ``capabilities`` field
    both funnel through this constructor so the two paths stay structurally
    identical — each item is exactly ``{"name", "type", "description"}``.
    Entries may be ``CapabilityMarketEntry`` ORM rows or ``CapabilityInline``
    request schemas; both expose ``name`` / ``type`` / ``description``.
    """
    return [
        {
            "name": entry.name,
            "type": entry.type,
            "description": entry.description,
        }
        for entry in entries
    ]


def capability_to_dict(cap: CapabilityMarketEntry) -> dict[str, Any]:
    """Shape a market row like the legacy ``entities.capabilities`` JSONB item."""
    out: dict[str, Any] = {"name": cap.name, "type": cap.type}
    if cap.description:
        out["description"] = cap.description
    if cap.config_template:
        out["config_template"] = cap.config_template
    return out


def _gene_inline_to_dict(item: dict[str, Any]) -> dict[str, Any]:
    """Shape an AiGene manifest inline capability like a market capability.

    Inline entries only carry ``name`` / ``type`` / ``description`` (v4.9
    A2a shape — no ``config_template``). ``type`` defaults to ``"skill"``
    to match :func:`mirror_arrays`' fallback.
    """
    out: dict[str, Any] = {
        "name": item["name"],
        "type": item.get("type") or "skill",
    }
    if item.get("description"):
        out["description"] = item["description"]
    return out


async def _load_entity_gene_inline_capability_dicts(
    db: AsyncSession, entity_id: str, preset_slug: str | None
) -> list[dict[str, Any]]:
    """Expand inline ``capabilities`` from every gene attached to an entity.

    Genes attached explicitly via ``entity_ai_genes`` and genes inherited
    from the BaseClass referenced by *preset_slug* both contribute; a gene
    slug present in both sources is expanded once (explicit wins, matching
    :func:`load_entity_ai_gene_dicts`). Manifests are read in two JOIN
    queries — no per-gene round trips.
    """
    from app.schemas.ai_gene import extract_manifest_capabilities

    genes: dict[str, dict | None] = {}
    explicit_result = await db.execute(
        select(AiGene.slug, AiGene.manifest)
        .join(EntityAiGene, EntityAiGene.ai_gene_id == AiGene.id)
        .where(
            EntityAiGene.entity_id == entity_id,
            EntityAiGene.deleted_at.is_(None),
            AiGene.deleted_at.is_(None),
        )
    )
    for slug, manifest in explicit_result.all():
        genes[slug] = manifest

    if preset_slug:
        base_result = await db.execute(
            select(BaseClass).where(
                BaseClass.slug == preset_slug,
                BaseClass.deleted_at.is_(None),
            )
        )
        base_class = base_result.scalar_one_or_none()
        if base_class is not None:
            inherited_result = await db.execute(
                select(AiGene.slug, AiGene.manifest)
                .join(BaseClassAiGene, BaseClassAiGene.ai_gene_id == AiGene.id)
                .where(
                    BaseClassAiGene.base_class_id == base_class.id,
                    BaseClassAiGene.deleted_at.is_(None),
                    AiGene.deleted_at.is_(None),
                )
            )
            for slug, manifest in inherited_result.all():
                genes.setdefault(slug, manifest)

    out: list[dict[str, Any]] = []
    for manifest in genes.values():
        caps = extract_manifest_capabilities(manifest)
        if not caps:
            continue
        for item in caps:
            if isinstance(item, dict) and item.get("name"):
                out.append(_gene_inline_to_dict(item))
    return out


async def load_entity_capability_dicts(
    db: AsyncSession,
    entity_id: str,
    *,
    entity: Entity | None = None,
) -> list[dict[str, Any]]:
    """An Entity's effective capabilities as legacy-shaped dicts.

    Reads the ``entity_capabilities`` junction, then unions in the inline
    ``capabilities`` from every gene attached to the entity — explicit
    ``entity_ai_genes`` rows plus genes inherited from the BaseClass
    referenced by ``entity.preset_slug``. The union is deduplicated by
    capability ``name``: a capability present both on the junction and
    inline in a gene is injected once, with the junction row winning (it
    carries the richer market metadata such as ``config_template``).

    *entity* is accepted so callers that already hold the row can skip the
    by-id lookup; when omitted the entity is loaded to resolve the
    base-class inheritance chain.
    """
    result = await db.execute(
        select(CapabilityMarketEntry)
        .join(
            EntityCapability,
            EntityCapability.capability_id == CapabilityMarketEntry.id,
        )
        .where(
            EntityCapability.entity_id == entity_id,
            EntityCapability.deleted_at.is_(None),
            CapabilityMarketEntry.deleted_at.is_(None),
        )
        .order_by(CapabilityMarketEntry.name)
    )
    junction = [capability_to_dict(c) for c in result.scalars().all()]

    preset_slug: str | None = None
    if entity is not None:
        preset_slug = entity.preset_slug
    else:
        row = await db.get(Entity, entity_id)
        if row is not None and row.deleted_at is None:
            preset_slug = row.preset_slug

    gene_caps = await _load_entity_gene_inline_capability_dicts(
        db, entity_id, preset_slug
    )

    junction_names = {cap["name"] for cap in junction}
    merged = list(junction)
    for cap in gene_caps:
        if cap["name"] not in junction_names:
            junction_names.add(cap["name"])
            merged.append(cap)
    merged.sort(key=lambda cap: cap.get("name") or "")
    return merged


async def load_base_class_capability_dicts(
    db: AsyncSession, base_class_id: str
) -> list[dict[str, Any]]:
    """Junction-read: a BaseClass's capabilities as legacy-shaped dicts."""
    result = await db.execute(
        select(CapabilityMarketEntry)
        .join(
            BaseClassCapability,
            BaseClassCapability.capability_id == CapabilityMarketEntry.id,
        )
        .where(
            BaseClassCapability.base_class_id == base_class_id,
            BaseClassCapability.deleted_at.is_(None),
            CapabilityMarketEntry.deleted_at.is_(None),
        )
        .order_by(CapabilityMarketEntry.name)
    )
    return [capability_to_dict(c) for c in result.scalars().all()]


async def load_entity_gene_refs(db: AsyncSession, entity_id: str) -> list[str]:
    """Junction-read: AiGene slugs attached to an Entity."""
    result = await db.execute(
        select(AiGene.slug)
        .join(EntityAiGene, EntityAiGene.ai_gene_id == AiGene.id)
        .where(
            EntityAiGene.entity_id == entity_id,
            EntityAiGene.deleted_at.is_(None),
            AiGene.deleted_at.is_(None),
        )
        .order_by(AiGene.slug)
    )
    return list(result.scalars().all())


async def load_entity_ai_gene_dicts(
    db: AsyncSession, entity: Entity
) -> list[dict[str, Any]]:
    """Junction-read: an Entity's AI genes as ``{"slug", "source"}`` dicts.

    Genes attached explicitly via the ``entity_ai_genes`` junction are
    reported with ``source="extra_added"``. Genes attached to the BaseClass
    referenced by ``entity.preset_slug`` are inherited with
    ``source="from_base_class"`` (base-class lookup by slug, matching the
    codebase's other preset resolution paths — the slug index is global so
    no extra org scoping is needed). A slug present in both sources is
    reported once, with the explicit ``extra_added`` attachment winning.
    """
    explicit: list[dict[str, Any]] = []
    result = await db.execute(
        select(AiGene.slug)
        .join(EntityAiGene, EntityAiGene.ai_gene_id == AiGene.id)
        .where(
            EntityAiGene.entity_id == entity.id,
            EntityAiGene.deleted_at.is_(None),
            AiGene.deleted_at.is_(None),
        )
        .order_by(AiGene.slug)
    )
    explicit = [
        {"slug": slug, "source": "extra_added"} for slug in result.scalars().all()
    ]

    inherited: list[dict[str, Any]] = []
    if entity.preset_slug:
        base_result = await db.execute(
            select(BaseClass).where(
                BaseClass.slug == entity.preset_slug,
                BaseClass.deleted_at.is_(None),
            )
        )
        base_class = base_result.scalar_one_or_none()
        if base_class is not None:
            inherited_result = await db.execute(
                select(AiGene.slug)
                .join(BaseClassAiGene, BaseClassAiGene.ai_gene_id == AiGene.id)
                .where(
                    BaseClassAiGene.base_class_id == base_class.id,
                    BaseClassAiGene.deleted_at.is_(None),
                    AiGene.deleted_at.is_(None),
                )
                .order_by(AiGene.slug)
            )
            inherited = [
                {"slug": slug, "source": "from_base_class"}
                for slug in inherited_result.scalars().all()
            ]

    explicit_slugs = {gene["slug"] for gene in explicit}
    merged = list(explicit)
    merged.extend(gene for gene in inherited if gene["slug"] not in explicit_slugs)
    return merged


def mirror_arrays(cap_dicts: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Split capability dicts into the manifest mirror arrays.

    Commands are mirrored without the ``cmd-`` prefix (migration-spec §1
    aggregate read path).
    """
    skills: list[str] = []
    tools: list[str] = []
    commands: list[str] = []
    for cap in cap_dicts:
        name = cap.get("name") or ""
        cap_type = cap.get("type") or "skill"
        if cap_type == "command":
            commands.append(name.removeprefix("cmd-"))
        elif cap_type == "skill":
            skills.append(name)
        elif cap_type in ("tool", "mcp", "lsp"):
            tools.append(name)
    return {"skills": skills, "tools": tools, "commands": commands}


async def upsert_capability(
    db: AsyncSession,
    *,
    name: str,
    cap_type: str = "skill",
    scope: str = "org",
    organization_id: str | None = None,
    namespace_id: str | None = None,
    created_via: str = "manual",
    description: str | None = None,
    config_template: dict | None = None,
    source_entity_slug: str | None = None,
) -> CapabilityMarketEntry:
    """Idempotent upsert keyed on active ``name`` (partial unique)."""
    result = await db.execute(
        select(CapabilityMarketEntry).where(
            CapabilityMarketEntry.name == name,
            CapabilityMarketEntry.deleted_at.is_(None),
        )
    )
    cap = result.scalar_one_or_none()
    if cap is not None:
        return cap
    cap = CapabilityMarketEntry(
        name=name,
        type=cap_type if cap_type in _MIRROR_TYPES else "skill",
        scope=scope,
        organization_id=organization_id,
        namespace_id=namespace_id,
        created_via=created_via,
        description=description,
        config_template=config_template,
        source_entity_slug=source_entity_slug,
    )
    db.add(cap)
    await db.flush()
    return cap


async def attach_entity_capability(
    db: AsyncSession, *, entity_id: str, capability_id: str
) -> None:
    """Idempotently link an Entity to a capability."""
    result = await db.execute(
        select(EntityCapability).where(
            EntityCapability.entity_id == entity_id,
            EntityCapability.capability_id == capability_id,
            EntityCapability.deleted_at.is_(None),
        )
    )
    if result.scalar_one_or_none() is None:
        db.add(EntityCapability(entity_id=entity_id, capability_id=capability_id))
        await db.flush()


async def attach_base_class_capability(
    db: AsyncSession, *, base_class_id: str, capability_id: str
) -> None:
    """Idempotently link a BaseClass to a capability."""
    result = await db.execute(
        select(BaseClassCapability).where(
            BaseClassCapability.base_class_id == base_class_id,
            BaseClassCapability.capability_id == capability_id,
            BaseClassCapability.deleted_at.is_(None),
        )
    )
    if result.scalar_one_or_none() is None:
        db.add(
            BaseClassCapability(
                base_class_id=base_class_id, capability_id=capability_id
            )
        )
        await db.flush()


async def detach_entity_capability(
    db: AsyncSession, *, entity_id: str, capability_id: str
) -> None:
    """Soft-delete Entity ↔ capability junction."""
    result = await db.execute(
        select(EntityCapability).where(
            EntityCapability.entity_id == entity_id,
            EntityCapability.capability_id == capability_id,
            EntityCapability.deleted_at.is_(None),
        )
    )
    link = result.scalar_one_or_none()
    if link is None:
        raise NotFoundError(
            "entity.capability_not_attached",
            "errors.entity.capability_not_attached",
            f"Capability '{capability_id}' is not attached to entity '{entity_id}'",
        )
    link.soft_delete()
    await db.flush()


async def detach_base_class_capability(
    db: AsyncSession, *, base_class_id: str, capability_id: str
) -> None:
    """Soft-delete BaseClass ↔ capability junction."""
    result = await db.execute(
        select(BaseClassCapability).where(
            BaseClassCapability.base_class_id == base_class_id,
            BaseClassCapability.capability_id == capability_id,
            BaseClassCapability.deleted_at.is_(None),
        )
    )
    link = result.scalar_one_or_none()
    if link is None:
        raise NotFoundError(
            "base_class.capability_not_attached",
            "errors.base_class.capability_not_attached",
            f"Capability '{capability_id}' is not attached to base class '{base_class_id}'",
        )
    link.soft_delete()
    await db.flush()


async def attach_entity_ai_gene(
    db: AsyncSession, *, entity_id: str, ai_gene_id: str
) -> None:
    """Idempotently link an Entity to an AiGene."""
    result = await db.execute(
        select(EntityAiGene).where(
            EntityAiGene.entity_id == entity_id,
            EntityAiGene.ai_gene_id == ai_gene_id,
            EntityAiGene.deleted_at.is_(None),
        )
    )
    if result.scalar_one_or_none() is None:
        db.add(EntityAiGene(entity_id=entity_id, ai_gene_id=ai_gene_id))
        await db.flush()


async def detach_entity_ai_gene(
    db: AsyncSession, *, entity_id: str, ai_gene_id: str
) -> None:
    """Soft-delete Entity ↔ AiGene junction."""
    result = await db.execute(
        select(EntityAiGene).where(
            EntityAiGene.entity_id == entity_id,
            EntityAiGene.ai_gene_id == ai_gene_id,
            EntityAiGene.deleted_at.is_(None),
        )
    )
    link = result.scalar_one_or_none()
    if link is None:
        raise NotFoundError(
            "entity.ai_gene_not_attached",
            "errors.entity.ai_gene_not_attached",
            f"AiGene '{ai_gene_id}' is not attached to entity '{entity_id}'",
        )
    link.soft_delete()
    await db.flush()


async def attach_base_class_ai_gene(
    db: AsyncSession, *, base_class_id: str, ai_gene_id: str
) -> None:
    """Idempotently link a BaseClass to an AiGene."""
    result = await db.execute(
        select(BaseClassAiGene).where(
            BaseClassAiGene.base_class_id == base_class_id,
            BaseClassAiGene.ai_gene_id == ai_gene_id,
            BaseClassAiGene.deleted_at.is_(None),
        )
    )
    if result.scalar_one_or_none() is None:
        db.add(BaseClassAiGene(base_class_id=base_class_id, ai_gene_id=ai_gene_id))
        await db.flush()


async def detach_base_class_ai_gene(
    db: AsyncSession, *, base_class_id: str, ai_gene_id: str
) -> None:
    """Soft-delete BaseClass ↔ AiGene junction."""
    result = await db.execute(
        select(BaseClassAiGene).where(
            BaseClassAiGene.base_class_id == base_class_id,
            BaseClassAiGene.ai_gene_id == ai_gene_id,
            BaseClassAiGene.deleted_at.is_(None),
        )
    )
    link = result.scalar_one_or_none()
    if link is None:
        raise NotFoundError(
            "base_class.ai_gene_not_attached",
            "errors.base_class.ai_gene_not_attached",
            f"AiGene '{ai_gene_id}' is not attached to base class '{base_class_id}'",
        )
    link.soft_delete()
    await db.flush()


async def bump_entity_migration_hash(db: AsyncSession, entity: Entity) -> None:
    """Recompute and persist migration_hash for one Entity."""
    from app.core.migration_hash import compute_entity_migration_hash

    entity.migration_hash = await compute_entity_migration_hash(db, entity)
    await db.flush()


async def bump_entities_for_base_class(db: AsyncSession, base_class_slug: str) -> None:
    """Bump migration_hash for all active entities using *base_class_slug*."""
    result = await db.execute(
        select(Entity).where(
            Entity.preset_slug == base_class_slug,
            Entity.deleted_at.is_(None),
        )
    )
    for entity in result.scalars().all():
        await bump_entity_migration_hash(db, entity)


async def bump_entities_for_gene(db: AsyncSession, ai_gene_id: str) -> None:
    """Bump migration_hash for entities whose capability surface uses *ai_gene_id*.

    Covers entities that attach the gene explicitly via ``entity_ai_genes``
    and entities that inherit it through a BaseClass (each affected
    BaseClass's entities via :func:`bump_entities_for_base_class`). Used by
    the ai-genes update path when ``manifest["capabilities"]`` changes.
    """
    result = await db.execute(
        select(Entity)
        .join(EntityAiGene, EntityAiGene.entity_id == Entity.id)
        .where(
            EntityAiGene.ai_gene_id == ai_gene_id,
            EntityAiGene.deleted_at.is_(None),
            Entity.deleted_at.is_(None),
        )
    )
    for entity in result.scalars().all():
        await bump_entity_migration_hash(db, entity)

    base_classes = await db.execute(
        select(BaseClass)
        .join(BaseClassAiGene, BaseClassAiGene.base_class_id == BaseClass.id)
        .where(
            BaseClassAiGene.ai_gene_id == ai_gene_id,
            BaseClassAiGene.deleted_at.is_(None),
            BaseClass.deleted_at.is_(None),
        )
    )
    for base_class in base_classes.scalars().all():
        await bump_entities_for_base_class(db, base_class.slug)
