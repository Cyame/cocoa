"""Platform identity = locked human gene packs (PRD-v3-post).

Identity is NOT a parallel role table. Selecting an identity syncs a locked
pack of ``user_genes``; ``is_super_admin`` is derived from ``identity-system``.
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.user_gene import UserGene, UserUserGene

IdentityKey = Literal["system", "org", "namespace", "workspace", "member"]

IDENTITY_ORDER: tuple[IdentityKey, ...] = (
    "system",
    "org",
    "namespace",
    "workspace",
    "member",
)

IDENTITY_SLUGS: dict[IdentityKey, str] = {
    "system": "identity-system",
    "org": "identity-org",
    "namespace": "identity-namespace",
    "workspace": "identity-workspace",
    "member": "identity-member",
}

# Each pack is currently a single gene; keep list shape for future expansion.
IDENTITY_PACKS: dict[IdentityKey, tuple[str, ...]] = {
    key: (slug,) for key, slug in IDENTITY_SLUGS.items()
}

ALL_IDENTITY_SLUGS: frozenset[str] = frozenset(IDENTITY_SLUGS.values())

LEGACY_GENE_MAP: dict[str, IdentityKey] = {
    "admin-gene": "system",
    "operator-gene": "workspace",
    "viewer-gene": "member",
    # auditor was cross-cutting; map to namespace management surface.
    "auditor-gene": "namespace",
}

IDENTITY_DEFS: dict[IdentityKey, dict] = {
    "system": {
        "name": "System Admin",
        "description": "Platform super-admin; full world / user / provider control",
        "permission_keys": [
            "can_manage_users",
            "can_manage_organization",
            "can_manage_namespaces",
            "can_manage_workspaces",
            "can_manage_providers",
            "can_manage_genes",
            "can_summon_entity",
            "can_spawn_instance",
            "can_interrupt_instance",
            "can_pause_instance",
            "can_edit_central_hub",
            "can_view_workspace",
            "can_view_topology",
            "can_view_audit_log",
            "can_export_audit_log",
            "can_create_workspace",
            "can_delete_workspace",
        ],
    },
    "org": {
        "name": "World Admin",
        "description": "Organization (world) management",
        "permission_keys": [
            "can_manage_organization",
            "can_manage_namespaces",
            "can_manage_workspaces",
            "can_summon_entity",
            "can_spawn_instance",
            "can_view_workspace",
            "can_view_topology",
            "can_create_workspace",
            "can_delete_workspace",
        ],
    },
    "namespace": {
        "name": "Namespace Admin",
        "description": "Namespace (scenario) management",
        "permission_keys": [
            "can_manage_namespaces",
            "can_manage_workspaces",
            "can_summon_entity",
            "can_spawn_instance",
            "can_view_workspace",
            "can_view_topology",
            "can_create_workspace",
        ],
    },
    "workspace": {
        "name": "Workspace Admin",
        "description": "Workspace operations",
        "permission_keys": [
            "can_manage_workspaces",
            "can_summon_entity",
            "can_spawn_instance",
            "can_interrupt_instance",
            "can_pause_instance",
            "can_edit_central_hub",
            "can_view_workspace",
            "can_view_topology",
            "can_create_workspace",
        ],
    },
    "member": {
        "name": "Member",
        "description": "Baseline visibility and collaboration",
        "permission_keys": [
            "can_view_workspace",
            "can_view_topology",
            "can_view_audit_log",
        ],
    },
}

# Flat catalog of can_* slugs used by human genes / 契印 UI.
ALL_PERMISSION_KEYS: tuple[str, ...] = tuple(
    sorted(
        {
            key
            for meta in IDENTITY_DEFS.values()
            for key in meta["permission_keys"]
        }
    )
)


def identity_key_from_slug(slug: str) -> IdentityKey | None:
    for key, gene_slug in IDENTITY_SLUGS.items():
        if gene_slug == slug:
            return key
    mapped = LEGACY_GENE_MAP.get(slug)
    return mapped


def rank_of(identity: IdentityKey) -> int:
    """Lower number = higher privilege."""
    return IDENTITY_ORDER.index(identity)


def highest_identity(keys: set[IdentityKey]) -> IdentityKey | None:
    if not keys:
        return None
    return min(keys, key=rank_of)


async def _active_gene_links(
    db: AsyncSession, user_id: str
) -> list[tuple[UserUserGene, UserGene]]:
    result = await db.execute(
        select(UserUserGene, UserGene)
        .join(UserGene, UserGene.id == UserUserGene.user_gene_id)
        .where(
            UserUserGene.user_id == user_id,
            UserUserGene.deleted_at.is_(None),
            UserGene.deleted_at.is_(None),
        )
    )
    return list(result.all())


async def resolve_user_identity(
    db: AsyncSession, user_id: str
) -> tuple[IdentityKey | None, list[str], list[str]]:
    """Return (highest identity, locked gene slugs, extra gene slugs)."""
    rows = await _active_gene_links(db, user_id)
    identity_keys: set[IdentityKey] = set()
    locked: list[str] = []
    extras: list[str] = []
    for _link, gene in rows:
        key = identity_key_from_slug(gene.slug)
        if key is not None or gene.slug in ALL_IDENTITY_SLUGS:
            if key is not None:
                identity_keys.add(key)
            locked.append(gene.slug)
        else:
            extras.append(gene.slug)
    return highest_identity(identity_keys), locked, extras


async def user_meets_identity(
    db: AsyncSession, user: User, min_identity: IdentityKey
) -> bool:
    """True if user has identity at least as privileged as *min_identity*."""
    if user.is_super_admin:
        return True
    current, _, _ = await resolve_user_identity(db, user.id)
    if current is None:
        return False
    return rank_of(current) <= rank_of(min_identity)


async def sync_identity_pack(
    db: AsyncSession,
    user: User,
    identity: IdentityKey,
    *,
    commit: bool = False,
) -> None:
    """Replace locked identity genes with the pack for *identity*; sync flag."""
    pack_slugs = set(IDENTITY_PACKS[identity])
    all_identity = set(ALL_IDENTITY_SLUGS) | set(LEGACY_GENE_MAP.keys())

    genes = (
        await db.execute(
            select(UserGene).where(
                UserGene.slug.in_(pack_slugs | all_identity),
                UserGene.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    by_slug = {g.slug: g for g in genes}

    links = (
        await db.execute(
            select(UserUserGene).where(
                UserUserGene.user_id == user.id,
                UserUserGene.deleted_at.is_(None),
            )
        )
    ).scalars().all()

    gene_ids_by_id = {
        g.id: g
        for g in (
            await db.execute(
                select(UserGene).where(
                    UserGene.id.in_([link.user_gene_id for link in links] or ["__none__"]),
                    UserGene.deleted_at.is_(None),
                )
            )
        ).scalars().all()
    }

    attached_pack: set[str] = set()
    for link in links:
        gene = gene_ids_by_id.get(link.user_gene_id)
        if gene is None:
            continue
        if gene.slug in all_identity or gene.slug in ALL_IDENTITY_SLUGS:
            if gene.slug in pack_slugs:
                attached_pack.add(gene.slug)
            else:
                link.soft_delete()

    for slug in pack_slugs:
        if slug in attached_pack:
            continue
        gene = by_slug.get(slug)
        if gene is None:
            continue
        db.add(UserUserGene(user_id=user.id, user_gene_id=gene.id))

    user.is_super_admin = identity == "system"
    if commit:
        await db.commit()
        await db.refresh(user)


async def ensure_identity_genes(db: AsyncSession) -> dict[str, UserGene]:
    """Upsert the five identity genes; return slug → gene."""
    out: dict[str, UserGene] = {}
    for key, slug in IDENTITY_SLUGS.items():
        meta = IDENTITY_DEFS[key]
        existing = (
            await db.execute(
                select(UserGene).where(
                    UserGene.slug == slug,
                    UserGene.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            gene = UserGene(
                slug=slug,
                name=meta["name"],
                kind="builtin",
                permission_keys=list(meta["permission_keys"]),
                description=meta["description"],
            )
            db.add(gene)
            await db.flush()
            out[slug] = gene
        else:
            existing.name = meta["name"]
            existing.permission_keys = list(meta["permission_keys"])
            existing.description = meta["description"]
            out[slug] = existing
    await ensure_permission_genes(db)
    return out


async def ensure_permission_genes(db: AsyncSession) -> dict[str, UserGene]:
    """Upsert one attachable gene per can_* permission key (extra-gene catalog)."""
    out: dict[str, UserGene] = {}
    for key in ALL_PERMISSION_KEYS:
        existing = (
            await db.execute(
                select(UserGene).where(
                    UserGene.slug == key,
                    UserGene.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            gene = UserGene(
                slug=key,
                name=key,
                kind="builtin",
                permission_keys=[key],
                description=f"Permission: {key}",
            )
            db.add(gene)
            await db.flush()
            out[key] = gene
        else:
            existing.permission_keys = [key]
            if not existing.name:
                existing.name = key
            out[key] = existing
    return out
