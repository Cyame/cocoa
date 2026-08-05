"""Agent config overlay — BaseClass template ⊕ Entity identity (PRD-v2).

Semantics (must not conflate):

* **system_prompt**: BaseClass is a *static operating-form template*. Entity
  ``NULL`` inherits; non-``NULL`` replaces. World-hub may later rewrite the
  composed prompt (see ``prompt_compose``).
* **capabilities / genes**: **Entity-authoritative only** — never a union with
  BaseClass defaults. BaseClass is a static template for identity/prompt, not
  the live capability source.
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


def _manifest_template_subset(manifest: dict[str, Any]) -> dict[str, Any]:
    """Static BaseClass template fields (prompt / model / commands / tools).

    Does **not** copy capabilities or gene_refs — those come from Entity only.
    """
    return {
        "provider_config": manifest.get("provider_config") or {},
        "default_model": manifest.get("default_model")
        or manifest.get("model")
        or "tbd",
        "commands": list(manifest.get("commands") or []),
        "system_prompt": manifest.get("system_prompt")
        or manifest.get("prompt")
        or "",
        "tools": list(manifest.get("tools") or []),
        "runtime_config": dict(manifest.get("runtime_config") or {}),
        # Template-only copies for world-hub prompt composition (not live caps).
        "baseclass_template_prompt": manifest.get("system_prompt")
        or manifest.get("prompt")
        or "",
        "baseclass_operating_form": manifest.get("operating_form")
        or manifest.get("description")
        or "",
    }


def resolve_entity_config(
    entity: Entity,
    base_manifest: dict[str, Any] | None,
    *,
    capabilities: list[Any] | None = None,
    gene_refs: list[Any] | None = None,
) -> dict[str, Any]:
    """Resolve overlay without DB access (manifest already loaded).

    v4.0: Entity capabilities / gene refs come from the junction tables —
    callers pass them preloaded via *capabilities* / *gene_refs* (see
    :func:`resolve_instance_agent_config`). ``config_override`` lists still
    win when explicitly present.
    """
    resolved = _manifest_template_subset(base_manifest or {})

    # Prompt: Entity replaces when set; else inherit BaseClass template.
    if entity.system_prompt is not None:
        resolved["system_prompt"] = entity.system_prompt

    # Capabilities / genes: Entity only — never union with BaseClass.
    override = dict(entity.config_override or {})
    # Strip capability/gene keys from deep_merge so BaseClass cannot leak back
    # if someone stuffed them into override incorrectly after we set Entity.
    cap_keys = {
        "default_capabilities",
        "capabilities",
        "default_gene_refs",
        "gene_refs",
        "installed_genes",
    }
    merge_overlay = {k: v for k, v in override.items() if k not in cap_keys}
    if merge_overlay:
        resolved = deep_merge(resolved, merge_overlay)

    # Explicit Entity-side capability/gene assignment (override list wins if present).
    if "default_capabilities" in override and isinstance(
        override["default_capabilities"], list
    ):
        resolved["default_capabilities"] = list(override["default_capabilities"])
    elif "capabilities" in override and isinstance(override["capabilities"], list):
        resolved["default_capabilities"] = list(override["capabilities"])
    else:
        resolved["default_capabilities"] = list(capabilities or [])

    refs: list[Any] | None = None
    if override:
        for key in ("default_gene_refs", "gene_refs", "installed_genes"):
            val = override.get(key)
            if isinstance(val, list):
                refs = list(val)
                break
    resolved["default_gene_refs"] = refs if refs is not None else list(gene_refs or [])

    resolved["entity_slug"] = entity.slug
    resolved["entity_name"] = entity.display_name or entity.name
    resolved["entity_role_prompt"] = entity.system_prompt  # may be None

    return resolved


async def resolve_instance_agent_config(
    db: AsyncSession,
    entity: Entity,
) -> dict[str, Any]:
    """Load BaseClass by ``entity.preset_slug`` and resolve the config subset.

    v4.0: capabilities / gene refs are JOINed from the junction tables.
    """
    from app.core.capabilities import (
        load_entity_capability_dicts,
        load_entity_gene_refs,
    )

    capabilities = await load_entity_capability_dicts(db, entity.id, entity=entity)
    gene_refs = await load_entity_gene_refs(db, entity.id)

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
            resolved = resolve_entity_config(
                entity, manifest, capabilities=capabilities, gene_refs=gene_refs
            )
            resolved["baseclass_slug"] = preset.slug
            resolved["baseclass_name"] = preset.display_name or preset.name
            return resolved

    return resolve_entity_config(
        entity, manifest, capabilities=capabilities, gene_refs=gene_refs
    )
