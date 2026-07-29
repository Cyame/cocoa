"""Agent config overlay — BaseClass.manifest ⊕ Entity fields (PRD-v2).

Resolves the effective agent configuration subset used when spawning or
deploying an Instance:

    BaseClass.manifest  (base template)
    ⊕ Entity.system_prompt  (NULL → inherit from manifest)
    ⊕ Entity.config_override  (deep-merge overlay)
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base_class import BaseClass
from app.models.entity import Entity


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *override* onto a copy of *base*."""
    result = deepcopy(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _manifest_subset(manifest: dict[str, Any]) -> dict[str, Any]:
    """Extract the agent-config subset from a BaseClass manifest."""
    return {
        "provider_config": manifest.get("provider_config") or {},
        "default_model": manifest.get("default_model")
        or manifest.get("model")
        or "tbd",
        "commands": list(manifest.get("commands") or []),
        "default_capabilities": list(
            manifest.get("default_capabilities") or manifest.get("skills") or []
        ),
        "default_gene_refs": list(
            manifest.get("default_gene_refs")
            or manifest.get("installed_genes")
            or manifest.get("gene_refs")
            or []
        ),
        "system_prompt": manifest.get("system_prompt")
        or manifest.get("prompt")
        or "",
        "tools": list(manifest.get("tools") or []),
        "runtime_config": dict(manifest.get("runtime_config") or {}),
    }


def resolve_entity_config(
    entity: Entity,
    base_manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    """Resolve overlay without DB access (manifest already loaded)."""
    resolved = _manifest_subset(base_manifest or {})

    if entity.system_prompt is not None:
        resolved["system_prompt"] = entity.system_prompt

    if entity.config_override:
        resolved = deep_merge(resolved, entity.config_override)

    return resolved


async def resolve_instance_agent_config(
    db: AsyncSession,
    entity: Entity,
) -> dict[str, Any]:
    """Load BaseClass by ``entity.preset_slug`` and resolve the config subset."""
    manifest: dict[str, Any] | None = None
    if entity.preset_slug:
        result = await db.execute(
            select(BaseClass).where(
                BaseClass.slug == entity.preset_slug,
                BaseClass.deleted_at.is_(None),
            )
        )
        preset = result.scalar_one_or_none()
        if preset is not None and isinstance(preset.manifest, dict):
            manifest = preset.manifest

    return resolve_entity_config(entity, manifest)
