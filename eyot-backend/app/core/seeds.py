"""System-level idempotent seeder (default org + builtin BaseClasses + atoms + cmd capabilities).

Introduced during the Cocoa → Eyot rename: the old incremental Alembic chain
seeded default data *interleaved* with schema DDL. After that history was
squashed into a single schema-only baseline (``Base.metadata.create_all``),
this module restores the essential default *data* at startup so a freshly
created database (production, dev, or a test clone) is fully functional.

Keeps Alembic schema-only and data idempotent at the app layer (modern
pattern). Every ``ensure_*`` is a no-op on an already-seeded database.

Invoked from:
  - ``app.main`` lifespan (after ``ensure_knowledge_seeds``) for prod/dev
  - the pytest ``_template_db`` fixture, so every cloned test DB inherits
    the same default seed state.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.builtin_presets import ALL_BUILTIN_PRESETS
from app.core.capabilities import attach_base_class_capability, upsert_capability
from app.core.gene_atoms import ensure_atom_genes
from app.models.base_class import BaseClass
from app.models.organization import Namespace, Organization

DEFAULT_ORG_SLUG = "default"
DEFAULT_ORG_NAME = "Default World"

# Internal, non-listed 始祖: the per-Workspace 小脑 (CentralHub's system agent).
CEREBELLUM_SLUG = "cerebellum-baseclass"
_CEREBELLUM_MANIFEST: dict = {
    "model": "tbd",
    "prompt": (
        "你是 Eyot 生境的中央智能体（小脑 / Cerebellum）, 内建于信号塔。"
        "你协调各血脉、处理未连线 @ 请求、维护生境运转，不对外展示为普通始祖。"
    ),
    "skills": [],
    "tools": [],
    "commands": ["monitor", "manage"],
    "provider": None,
    "subagent_strategy": {"enabled": [], "constraints": {"max_parallel": 1}},
}


async def ensure_default_organization(db: AsyncSession) -> Organization:
    """Create the single-tenant default Organization if absent."""
    org = (
        await db.execute(
            select(Organization).where(
                Organization.slug == DEFAULT_ORG_SLUG,
                Organization.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if org is None:
        org = Organization(slug=DEFAULT_ORG_SLUG, name=DEFAULT_ORG_NAME)
        db.add(org)
        await db.flush()
    return org


async def ensure_default_namespace(db: AsyncSession, org: Organization) -> Namespace:
    """Create the ``default`` Namespace under the default Organization if absent.

    ``app.core.tenant.get_default_namespace`` resolves workspaces/instances
    to this row; without it POST /workspaces fails with namespace.not_found.
    """
    ns = (
        await db.execute(
            select(Namespace).where(
                Namespace.org_id == org.id,
                Namespace.slug == "default",
                Namespace.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if ns is None:
        ns = Namespace(
            org_id=org.id,
            slug="default",
            name="Default Scenario",
        )
        db.add(ns)
        await db.flush()
    return ns


async def ensure_builtin_base_classes(db: AsyncSession) -> dict[str, BaseClass]:
    """Upsert the built-in 始祖 (BaseClass) templates as ``scope=system`` rows.

    Returns ``slug → BaseClass`` so callers can wire junctions.
    """
    out: dict[str, BaseClass] = {}
    for preset in ALL_BUILTIN_PRESETS:
        slug = preset["slug"]
        existing = (
            await db.execute(
                select(BaseClass).where(
                    BaseClass.slug == slug,
                    BaseClass.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            out[slug] = existing
            continue
        bc = BaseClass(
            slug=slug,
            name=preset["name"],
            display_name=preset.get("display_name"),
            description=preset.get("description"),
            manifest=preset.get("manifest"),
            version=preset.get("version"),
            tags=preset.get("tags"),
            scope="system",
            organization_id=None,
        )
        db.add(bc)
        await db.flush()
        out[slug] = bc
    return out


async def ensure_command_capabilities(
    db: AsyncSession, base_classes: dict[str, BaseClass]
) -> None:
    """Seed ``cmd-<verb>`` capabilities and wire them to their base_classes.

    Mirrors the old v4.0 migration's ``builtin commands → cmd-* capabilities +
    BaseClass junctions`` step, derived now from the live preset manifests.
    """
    verbs: set[str] = set()
    per_slug: dict[str, list[str]] = {}
    for preset in ALL_BUILTIN_PRESETS:
        commands = (preset.get("manifest") or {}).get("commands", []) or []
        per_slug[preset["slug"]] = commands
        verbs.update(commands)

    for verb in sorted(verbs):
        cap = await upsert_capability(
            db,
            name=f"cmd-{verb}",
            cap_type="command",
            scope="system",
            description=f"Built-in command: {verb}",
        )
        for slug, commands in per_slug.items():
            if verb in commands:
                bc = base_classes.get(slug)
                if bc is not None:
                    await attach_base_class_capability(
                        db, base_class_id=bc.id, capability_id=cap.id
                    )


async def ensure_cerebellum_baseclass(db: AsyncSession) -> None:
    """Ensure the internal 小脑 (Cerebellum) BaseClass exists.

    Hidden from the default catalogue (tags contain ``internal``+``system``);
    surfaced only with ``include_internal=true``.
    """
    existing = (
        await db.execute(
            select(BaseClass).where(
                BaseClass.slug == CEREBELLUM_SLUG,
                BaseClass.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    db.add(
        BaseClass(
            slug=CEREBELLUM_SLUG,
            name="小脑",
            display_name="小脑",
            description="内置中央智能体（信号塔 1:1）",
            manifest=_CEREBELLUM_MANIFEST,
            version="1.0.0",
            tags=["internal", "system"],
            scope="system",
            organization_id=None,
        )
    )
    await db.flush()


async def ensure_system_seeds(db: AsyncSession) -> None:
    """Idempotently ensure the full default system data set, then commit."""
    org = await ensure_default_organization(db)
    await ensure_default_namespace(db, org)
    await ensure_atom_genes(db)
    bcs = await ensure_builtin_base_classes(db)
    await ensure_command_capabilities(db, bcs)
    await ensure_cerebellum_baseclass(db)
    await db.commit()