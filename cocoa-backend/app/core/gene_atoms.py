"""Atomic permission (觉醒基因) catalog — single runtime source (v4.0).

The 16 atoms mirror the migration seed in
``alembic/versions/b3c626105a7e_v4_0_schema_scope_contracts_junctions.py``.
Keep both copies in sync when the catalog changes.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_gene import UserGene, UserGeneEffectScope

# slug → effect_scope
ATOM_CATALOG: dict[str, str] = {
    "can_manage_organization": UserGeneEffectScope.org.value,
    "can_manage_org_members": UserGeneEffectScope.org.value,
    "can_manage_namespace": UserGeneEffectScope.namespace.value,
    "can_manage_workspace": UserGeneEffectScope.workspace.value,
    "can_edit_workspace": UserGeneEffectScope.workspace.value,
    "can_view_workspace": UserGeneEffectScope.workspace.value,
    "can_operate_workspace": UserGeneEffectScope.workspace.value,
    "can_manage_genes": UserGeneEffectScope.org.value,
    "can_manage_capabilities": UserGeneEffectScope.org.value,
    "can_manage_ai_genes": UserGeneEffectScope.org.value,
    "can_clone_base_class": UserGeneEffectScope.org.value,
    "can_clone_entity": UserGeneEffectScope.namespace.value,
    "can_clone_organization": UserGeneEffectScope.org.value,
    "can_clone_workspace": UserGeneEffectScope.workspace.value,
    "can_manage_knowledge": UserGeneEffectScope.org.value,
    "can_manage_meetings": UserGeneEffectScope.workspace.value,
}

#: Atoms granted to a user who creates their own Organization (design §3.6:
#: 自建 Org 授予全部 effect_scope∈{org,namespace,workspace} — currently all).
ORG_OWNER_ATOMS: tuple[str, ...] = tuple(ATOM_CATALOG.keys())


async def ensure_atom_genes(db: AsyncSession) -> dict[str, UserGene]:
    """Idempotently upsert the atomic permission catalog. Returns slug → gene."""
    out: dict[str, UserGene] = {}
    for slug, scope in ATOM_CATALOG.items():
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
                name=slug,
                kind="builtin",
                effect_scope=scope,
                description=f"Atomic permission: {slug}",
            )
            db.add(gene)
            await db.flush()
            out[slug] = gene
        else:
            existing.effect_scope = scope
            existing.kind = "builtin"
            out[slug] = existing
    return out
