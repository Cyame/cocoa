"""Capability junction read/write helpers (v4.0).

The write truth for "which capabilities an Entity / BaseClass has" is the
junction tables; API responses still expose aggregated mirror arrays
(``manifest.skills/tools/commands``) for one-generation Portal compatibility.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_gene import AiGene
from app.models.capability_market import CapabilityMarketEntry
from app.models.junctions import (
    BaseClassCapability,
    EntityAiGene,
    EntityCapability,
)

_MIRROR_TYPES = ("skill", "tool", "mcp", "lsp", "command")


def capability_to_dict(cap: CapabilityMarketEntry) -> dict[str, Any]:
    """Shape a market row like the legacy ``entities.capabilities`` JSONB item."""
    out: dict[str, Any] = {"name": cap.name, "type": cap.type}
    if cap.description:
        out["description"] = cap.description
    if cap.config_template:
        out["config_template"] = cap.config_template
    return out


async def load_entity_capability_dicts(
    db: AsyncSession, entity_id: str
) -> list[dict[str, Any]]:
    """Junction-read: an Entity's capabilities as legacy-shaped dicts."""
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
    return [capability_to_dict(c) for c in result.scalars().all()]


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
