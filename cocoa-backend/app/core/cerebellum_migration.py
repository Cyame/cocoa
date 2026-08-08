"""Cerebellum legacy migration — v4-0 migration-spec §6.3 + §8.8 tiebreak.

Converts live ``cerebellum_agents`` rows into ``Entity(is_cerebellum=True)``
+ ``Instance`` rows. Two entry points share the same algorithm intent:

- :func:`migrate_cerebellum` — a **plain-sync** core-SQL function the Alembic
  revision runs inside the migration transaction via ``op.get_bind()``.
  It is also unit-testable against an async connection via
  ``await conn.run_sync(migrate_cerebellum)``.
- :func:`ensure_cerebellum_entity_and_instance` — the **runtime** helper used
  by the workspace-create hook and the ``central-hubs/{wid}/cerebellum``
  read/write path. Idempotent: finds the namespace cerebellum Entity (creates
  it when missing) and the workspace Instance (creates when missing).

The algorithm (per spec §6.3):

1. Resolve each active agent's hub → workspace → namespace.
2. One ``is_cerebellum`` Entity per namespace (partial unique
   ``uq_entities_cerebellum_per_ns``). §8.8 tiebreak: keep the agent with the
   latest ``heartbeat_at``, then latest ``created_at``, then highest id; the
   remaining agents still get Instances in their own workspaces.
3. One Instance per ``(entity_id, workspace_id)``, status mapped from the
   legacy ``loop_status``.
4. Soft-delete every migrated legacy row (no physical delete).

Merge conflicts emit a ``cerebellum.migration_merged`` audit event.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.workspace import generate_workspace_path
from app.models.central_hub import CentralHub, CerebellumAgent
from app.models.entity import Entity
from app.models.event import Event
from app.models.instance import Instance, InstanceStatus
from app.models.workspace import Workspace

logger = logging.getLogger(__name__)

LEGACY_AGENT = CerebellumAgent.__table__
CENTRAL_HUB = CentralHub.__table__
ENTITY = Entity.__table__
INSTANCE = Instance.__table__
WORKSPACE = Workspace.__table__
EVENT = Event.__table__

MERGED_EVENT_TYPE = "cerebellum.migration_merged"

# Legacy ``CerebellumAgent.loop_status`` → ``Instance.status`` (infra lifecycle).
# Legacy values come from the old harness loop vocabulary; idle means "agent
# alive, loop not active" → infra ``running``.
_LEGACY_STATUS_MAP: dict[str, str] = {
    "running": InstanceStatus.running.value,
    "idle": InstanceStatus.running.value,
    "restarting": InstanceStatus.restarting.value,
    "failed": InstanceStatus.failed.value,
    "paused": InstanceStatus.pending.value,
    "interrupted": InstanceStatus.pending.value,
    "completed": InstanceStatus.pending.value,
}


def map_legacy_loop_status(loop_status: str | None) -> str:
    """Map a legacy ``cerebellum_agents.loop_status`` to ``Instance.status``."""
    if not loop_status:
        return InstanceStatus.creating.value
    return _LEGACY_STATUS_MAP.get(loop_status, InstanceStatus.creating.value)


def _unique_slug(conn: sa.Connection, namespace_id: str, base: str) -> str:
    """Return *base* if free in the namespace, else a ``base-N`` suffix."""
    existing = {
        row[0]
        for row in conn.execute(
            sa.select(ENTITY.c.slug).where(
                ENTITY.c.namespace_id == namespace_id,
                ENTITY.c.deleted_at.is_(None),
            )
        )
    }
    if base not in existing:
        return base
    i = 2
    while f"{base}-{i}" in existing:
        i += 1
    return f"{base}-{i}"


def migrate_cerebellum(conn: sa.Connection) -> dict[str, Any]:
    """Migrate live ``cerebellum_agents`` rows to Entity + Instance.

    Runs inside a transaction (Alembic wraps ``op.get_bind()`` in one by
    default; callers may also drive it via ``run_sync`` + explicit commit).
    Never physically deletes rows. Returns a report dict.

    Idempotent: already-migrated agents are soft-deleted so a second run
    scans nothing; pre-existing Entity/Instance rows are reused.
    """
    agents = conn.execute(
        sa.select(LEGACY_AGENT).where(LEGACY_AGENT.c.deleted_at.is_(None))
    ).mappings().all()

    report: dict[str, Any] = {
        "scanned": len(agents),
        "entities_created": 0,
        "instances_created": 0,
        "merged": 0,
        "orphaned": 0,
    }
    if not agents:
        return report

    hubs = {
        row["id"]: row
        for row in conn.execute(sa.select(CENTRAL_HUB)).mappings()
        if row.get("deleted_at") is None
    }
    ws_ns = {
        row["id"]: row["namespace_id"]
        for row in conn.execute(
            sa.select(WORKSPACE.c.id, WORKSPACE.c.namespace_id)
        ).mappings()
    }

    by_ns: dict[str, list[dict[str, Any]]] = {}
    for agent in agents:
        hub = hubs.get(agent["central_hub_id"])
        if hub is None:
            report["orphaned"] += 1
            logger.warning(
                "cerebellum migration: agent %s has no active hub — skipped",
                agent["id"],
            )
            continue
        ns_id = ws_ns.get(hub["workspace_id"])
        if not ns_id:
            report["orphaned"] += 1
            logger.warning(
                "cerebellum migration: agent %s hub has no active workspace — skipped",
                agent["id"],
            )
            continue
        by_ns.setdefault(ns_id, []).append(agent)

    for ns_id, group in by_ns.items():
        # §8.8 tiebreak: latest heartbeat_at → latest created_at → highest id.
        group.sort(
            key=lambda a: (
                a.get("heartbeat_at") or datetime.min.replace(tzinfo=timezone.utc),
                a["created_at"],
                a["id"],
            ),
            reverse=True,
        )
        winner = group[0]

        entity_row = conn.execute(
            sa.select(ENTITY).where(
                ENTITY.c.namespace_id == ns_id,
                ENTITY.c.is_cerebellum.is_(True),
                ENTITY.c.deleted_at.is_(None),
            )
        ).mappings().first()

        if entity_row is None:
            entity_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            conn.execute(
                sa.insert(ENTITY).values(
                    id=entity_id,
                    namespace_id=ns_id,
                    name=winner.get("name") or "cerebellum",
                    slug=_unique_slug(conn, ns_id, "cerebellum"),
                    preset_slug=winner.get("base_slug") or "cerebellum-baseclass",
                    system_prompt=winner.get("system_prompt") or None,
                    is_cerebellum=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            report["entities_created"] += 1
        else:
            entity_id = entity_row["id"]
            # Never overwrite a non-empty prompt; backfill an empty one.
            if not entity_row.get("system_prompt") and winner.get("system_prompt"):
                conn.execute(
                    sa.update(ENTITY)
                    .where(ENTITY.c.id == entity_id)
                    .values(system_prompt=winner["system_prompt"])
                )

        for agent in group:
            ws_id = hubs[agent["central_hub_id"]]["workspace_id"]
            existing_inst = conn.execute(
                sa.select(INSTANCE).where(
                    INSTANCE.c.entity_id == entity_id,
                    INSTANCE.c.workspace_id == ws_id,
                    INSTANCE.c.deleted_at.is_(None),
                )
            ).mappings().first()
            if existing_inst is None:
                now = datetime.now(timezone.utc)
                conn.execute(
                    sa.insert(INSTANCE).values(
                        id=str(uuid.uuid4()),
                        entity_id=entity_id,
                        workspace_id=ws_id,
                        status=map_legacy_loop_status(agent.get("loop_status")),
                        created_at=now,
                        updated_at=now,
                    )
                )
                report["instances_created"] += 1

            if agent["id"] != winner["id"]:
                now = datetime.now(timezone.utc)
                conn.execute(
                    sa.insert(EVENT).values(
                        id=str(uuid.uuid4()),
                        type=MERGED_EVENT_TYPE,
                        actor_type="system",
                        actor_id=None,
                        resource_type="entity",
                        resource_id=entity_id,
                        payload={
                            "agent_id": agent["id"],
                            "namespace_id": ns_id,
                            "workspace_id": ws_id,
                        },
                        created_at=now,
                        updated_at=now,
                    )
                )
                report["merged"] += 1

        now = datetime.now(timezone.utc)
        for agent in group:
            conn.execute(
                sa.update(LEGACY_AGENT)
                .where(LEGACY_AGENT.c.id == agent["id"])
                .values(deleted_at=now)
            )

    return report


# ---------------------------------------------------------------------------
# Runtime read/write path
# ---------------------------------------------------------------------------


async def ensure_cerebellum_entity_and_instance(
    db: AsyncSession, workspace_id: str
) -> tuple[Entity, Instance]:
    """Idempotently ensure a workspace has its cerebellum Entity + Instance.

    Used by the workspace-create hook and the ``central-hubs`` cerebellum
    endpoints. The Entity is scoped per-namespace (one ``is_cerebellum`` per
    Namespace); the Instance is scoped per ``(entity, workspace)``.
    """
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None or workspace.deleted_at is not None:
        raise NotFoundError(
            "workspace.not_found",
            "errors.workspace.not_found",
            f"Workspace '{workspace_id}' not found",
        )

    entity = (
        await db.execute(
            sa.select(Entity).where(
                Entity.namespace_id == workspace.namespace_id,
                Entity.is_cerebellum.is_(True),
                Entity.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if entity is None:
        entity = Entity(
            namespace_id=workspace.namespace_id,
            name="cerebellum",
            slug=await _runtime_unique_slug(db, workspace.namespace_id, "cerebellum"),
            preset_slug="cerebellum-baseclass",
            system_prompt=None,
            is_cerebellum=True,
        )
        db.add(entity)
        await db.flush()

    instance = (
        await db.execute(
            sa.select(Instance).where(
                Instance.entity_id == entity.id,
                Instance.workspace_id == workspace_id,
                Instance.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if instance is None:
        instance = Instance(
            entity_id=entity.id,
            workspace_id=workspace_id,
            workspace_path=generate_workspace_path(entity.slug, str(uuid.uuid4())),
            status=InstanceStatus.creating.value,
            proxy_token=str(uuid.uuid4()),
        )
        db.add(instance)
        await db.flush()
    return entity, instance


async def _runtime_unique_slug(
    db: AsyncSession, namespace_id: str, base: str
) -> str:
    existing = {
        row
        for row in (
            await db.execute(
                sa.select(Entity.slug).where(
                    Entity.namespace_id == namespace_id,
                    Entity.deleted_at.is_(None),
                )
            )
        ).scalars()
    }
    if base not in existing:
        return base
    i = 2
    while f"{base}-{i}" in existing:
        i += 1
    return f"{base}-{i}"
