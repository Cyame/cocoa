"""Knowledge resolve + system seed ensure (v4.2 D16/H1 + M9).

Resolve semantics for an instance:

1. **Scope chain**: instance → ``entity_id`` → ``Namespace.org_id`` (mirrors
   ``app.services.llm.instance_pi_env._load_org_for_instance``).
2. **Visibility**: ``system`` rows (all ownership NULL) are always visible;
   org / namespace / workspace rows are visible only when they belong to the
   instance's org / namespace / workspace.
3. **Binding filter**: rows bound to a *different* ``entity_id`` /
   ``instance_id`` are excluded; unbound (NULL) rows and rows bound to the
   instance's own entity / instance are included.
4. **Override priority** (D16): for a key present at several scopes,
   ``workspace > namespace > org > system``.
5. **Same-scope tie** (H1): most recent ``updated_at`` wins, then ``id``
   (uuid, deterministic) — the query is ordered ``updated_at DESC, id DESC``
   and the first candidate at the winning scope is picked.

The system seeds (:data:`SYSTEM_SEEDS`) mirror the plan's optional seed rows
(``cocoa.collab.passage`` / ``cocoa.hub.shared_work``) and are ensured
idempotently at app startup.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import Entity
from app.models.instance import Instance
from app.models.knowledge import KnowledgeEntry
from app.models.organization import Namespace

logger = logging.getLogger(__name__)

#: Override priority — workspace wins over namespace over org over system (D16).
SCOPE_PRIORITY: dict[str, int] = {
    "workspace": 0,
    "namespace": 1,
    "org": 2,
    "system": 3,
}

#: System seed rows (scope=system, all ownership NULL) — plan §Seed.
SYSTEM_SEEDS: tuple[dict[str, str], ...] = (
    {
        "key": "cocoa.collab.passage",
        "title": "近邻通道协作约束",
        "body": (
            "化身只通过近邻消息通道与走廊内相邻的化身交换情报：消息仅送达直接相连"
            "的邻居，跨走廊的情报须经共享黑板上流转，禁止向非邻居化身直达。"
        ),
    },
    {
        "key": "cocoa.hub.shared_work",
        "title": "Hub 工作区约定",
        "body": (
            "Hub 中 shared 前缀路径为协作面，所有化身共享只读约定与产物；"
            "work 前缀路径为当前化身私有临时区，仅本人可读写，跨化身投递需显式"
            "复制到 shared。"
        ),
    },
)


async def _scope_chain(
    db: AsyncSession, instance: Instance
) -> tuple[str | None, str | None]:
    """Resolve ``(org_id, namespace_id)`` following instance → entity → namespace."""
    entity = await db.get(Entity, instance.entity_id)
    if entity is None or entity.deleted_at is not None:
        return None, None
    namespace = await db.get(Namespace, entity.namespace_id)
    if namespace is None or namespace.deleted_at is not None:
        return None, entity.namespace_id
    return namespace.org_id, entity.namespace_id


def _visibility_clause(
    org_id: str | None,
    ns_id: str | None,
    ws_id: str | None,
):
    """Rows visible to the instance's org / namespace / workspace chain."""
    if org_id is None:
        return KnowledgeEntry.scope == "system"
    return or_(
        KnowledgeEntry.scope == "system",
        and_(
            KnowledgeEntry.scope == "org",
            KnowledgeEntry.organization_id == org_id,
        ),
        and_(
            KnowledgeEntry.scope == "namespace",
            KnowledgeEntry.organization_id == org_id,
            KnowledgeEntry.namespace_id == ns_id,
        ),
        and_(
            KnowledgeEntry.scope == "workspace",
            KnowledgeEntry.organization_id == org_id,
            KnowledgeEntry.namespace_id == ns_id,
            KnowledgeEntry.workspace_id == ws_id,
        ),
    )


def _binding_clause(instance: Instance):
    """Unbound rows + rows bound to this instance's own entity / instance."""
    return and_(
        or_(
            KnowledgeEntry.entity_id.is_(None),
            KnowledgeEntry.entity_id == instance.entity_id,
        ),
        or_(
            KnowledgeEntry.instance_id.is_(None),
            KnowledgeEntry.instance_id == instance.id,
        ),
    )


def entry_to_dict(entry: KnowledgeEntry) -> dict[str, Any]:
    """Serialize a resolved entry for the API response."""
    return {
        "id": entry.id,
        "key": entry.key,
        "title": entry.title,
        "body": entry.body,
        "scope": entry.scope,
        "dimension_id": entry.dimension_id,
        "organization_id": entry.organization_id,
        "namespace_id": entry.namespace_id,
        "workspace_id": entry.workspace_id,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
    }


async def resolve_knowledge_for_instance(
    db: AsyncSession, instance: Instance | str
) -> list[KnowledgeEntry]:
    """Resolve the visible knowledge rows for an instance (D16/H1).

    Accepts either an :class:`Instance` ORM object or an instance id string.
    Returns at most one row per key — the override winner (highest-priority
    scope, then most recent ``updated_at``, then ``id``).
    """
    if isinstance(instance, str):
        inst = await db.get(Instance, instance)
        if inst is None or inst.deleted_at is not None:
            return []
    else:
        inst = instance

    org_id, ns_id = await _scope_chain(db, inst)
    ws_id = inst.workspace_id

    result = await db.execute(
        select(KnowledgeEntry)
        .where(
            KnowledgeEntry.deleted_at.is_(None),
            _visibility_clause(org_id, ns_id, ws_id),
            _binding_clause(inst),
        )
        .order_by(
            KnowledgeEntry.updated_at.desc(),
            KnowledgeEntry.id.desc(),
        )
    )
    rows = list(result.scalars().all())

    # Group per key; the query order (updated_at DESC, id DESC) makes the first
    # candidate at the winning scope the deterministic tie-break winner.
    groups: dict[str, list[KnowledgeEntry]] = {}
    for row in rows:
        groups.setdefault(row.key, []).append(row)

    winners: list[KnowledgeEntry] = []
    for candidates in groups.values():
        best_rank = min(SCOPE_PRIORITY.get(c.scope, 99) for c in candidates)
        for candidate in candidates:
            if SCOPE_PRIORITY.get(candidate.scope, 99) == best_rank:
                winners.append(candidate)
                break
    return winners


async def ensure_knowledge_seeds(db: AsyncSession) -> dict[str, KnowledgeEntry]:
    """Idempotently ensure the system seed knowledge rows exist.

    Mirrors ``app.core.gene_atoms.ensure_atom_genes`` — safe to run at every
    startup; a seed already present (active, scope=system) is left untouched.
    """
    out: dict[str, KnowledgeEntry] = {}
    for seed in SYSTEM_SEEDS:
        existing = (
            await db.execute(
                select(KnowledgeEntry).where(
                    KnowledgeEntry.key == seed["key"],
                    KnowledgeEntry.scope == "system",
                    KnowledgeEntry.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            entry = KnowledgeEntry(
                key=seed["key"],
                title=seed["title"],
                body=seed["body"],
                scope="system",
            )
            db.add(entry)
            await db.flush()
            out[seed["key"]] = entry
        else:
            out[seed["key"]] = existing
    return out
