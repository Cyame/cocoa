"""Shared factory for creating an introduced 迷失者 (Instance) with its Membership seat.

v5.0 extraction: ``workspaces.introduce_entity`` and ``instances.create_instance``
ran the same creation pipeline (workspace/entity validation → migration hash →
agent config resolution → knowledge payload → consistency hint → Instance row →
40x40 topology placement → audit events → commit). This module owns that
pipeline so the ``@`` no-instance introduce path (T4) can reuse it too.

The factory never writes authz (permission checks stay in the endpoint layer)
and never triggers deployment (best-effort auto-deploy stays in the
introduce endpoint, which owns the deploy service wiring).
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.core.event_types import INSTANCE_CREATED, INSTANCE_KNOWLEDGE_INCONSISTENT
from app.core.events import emit
from app.core.knowledge_spawn import (
    build_spawn_knowledge_payload,
    check_knowledge_consistency,
)
from app.core.migration_hash import compute_entity_migration_hash
from app.core.overlay import resolve_instance_agent_config
from app.core.workspace import generate_workspace_path
from app.models.entity import Entity
from app.models.instance import Instance, InstanceStatus
from app.models.workspace import Membership, Workspace

# Canonical conflict triples (error_code, message_key, message).
_CONFLICT_ALREADY_INTRODUCED: tuple[str, str, str] = (
    "instance.entity_already_introduced",
    "errors.instance.entity_already_introduced",
    "This entity already has a lost one in this workspace",
)


async def create_introduced_instance(
    db: AsyncSession,
    *,
    entity_id: str,
    workspace_id: str,
    workspace_path: str | None = None,
    runtime_config_override: dict[str, Any] | None = None,
    require_namespace_match: bool = False,
    ensure_migration_hash: bool = False,
    conflict_error: tuple[str, str, str] | None = None,
    actor_id: str | None = None,
) -> tuple[Instance, Membership, dict[str, list[str]] | None]:
    """Create an introduced Instance + its Membership seat in one transaction.

    Owns the full spawn pipeline shared by ``workspaces.introduce_entity``,
    ``instances.create_instance`` and the future ``@`` introduce gate:

    - validates workspace / entity existence (404) and, optionally, that the
      entity belongs to the workspace's namespace (409);
    - rejects duplicate active instances for the same (workspace, entity)
      with a 409 (``conflict_error`` triple, default introduce semantics);
    - optionally back-fills ``entity.migration_hash`` (introduce path);
    - resolves the agent config overlay, injects has-knowledge as
      ``runtime_config["knowledge"]`` and computes the non-blocking
      consistency hint;
    - creates the Instance in ``creating`` status with a fresh proxy token,
      places the Membership on the 40x40 topology grid (first free cell,
      stepping by 120), emits ``instance.created`` /
      ``instance.knowledge_inconsistent``, commits and refreshes.

    Difference points preserved via parameters (do not flatten them):

    - ``workspace_path`` / ``runtime_config_override``: only the instances
      ``POST /instances`` path accepts these from the request body;
    - ``require_namespace_match`` + ``ensure_migration_hash``: introduce-only
      semantics (entity must belong to the workspace namespace; live-status
      wants ``entity.migration_hash`` back-filled so outdated stays false);
    - ``conflict_error``: the two endpoints surface the duplicate-instance
      409 with different codes (``instance.entity_already_introduced`` vs
      ``instance.already_exists``).

    Returns ``(instance, membership, consistency_warning)`` — the warning is
    ``None`` or ``{"missing": [...]}`` and must be attached to the response
    by the caller (``InstanceOutWithToken.knowledge_consistency_warning``).
    """
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None or workspace.deleted_at is not None:
        raise NotFoundError(
            "workspace.not_found",
            "errors.workspace.not_found",
            f"Workspace '{workspace_id}' not found",
        )

    entity = await db.get(Entity, entity_id)
    if entity is None or entity.deleted_at is not None:
        raise NotFoundError(
            "entity.not_found",
            "errors.entity.not_found",
            f"Entity '{entity_id}' not found",
        )
    if require_namespace_match and entity.namespace_id != workspace.namespace_id:
        raise ConflictError(
            "entity.namespace_mismatch",
            "errors.entity.namespace_mismatch",
            "Entity does not belong to this workspace's namespace",
        )

    existing = await db.execute(
        select(Instance).where(
            Instance.workspace_id == workspace_id,
            Instance.entity_id == entity_id,
            Instance.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        code, message_key, message = conflict_error or _CONFLICT_ALREADY_INTRODUCED
        raise ConflictError(code, message_key, message)

    # Introduce path: back-fill entity.migration_hash so live-status outdated
    # stays false, and reuse the stored value as the instance's active_hash.
    # The instances path (ensure_migration_hash=False) always recomputes —
    # that is its historical semantics.
    if ensure_migration_hash:
        if not entity.migration_hash:
            entity.migration_hash = await compute_entity_migration_hash(db, entity)
        active_hash = entity.migration_hash
    else:
        active_hash = await compute_entity_migration_hash(db, entity)

    resolved_path = workspace_path or generate_workspace_path(
        entity.slug, str(uuid4())
    )
    agent_config = await resolve_instance_agent_config(db, entity)
    runtime_config = dict(runtime_config_override or {})
    runtime_config["agent_config"] = agent_config
    knowledge_payload = await build_spawn_knowledge_payload(
        db, entity=entity, workspace_id=workspace_id
    )
    if knowledge_payload is not None:
        runtime_config["knowledge"] = knowledge_payload
    consistency_warning = await check_knowledge_consistency(db, entity)

    instance = Instance(
        entity_id=entity_id,
        workspace_id=workspace_id,
        workspace_path=resolved_path,
        status=InstanceStatus.creating.value,
        runtime_config=runtime_config,
        proxy_token=str(uuid4()),
        active_hash=active_hash,
    )
    db.add(instance)
    await db.flush()

    # Place the new instance on the 40x40 workspace topology canvas: first
    # free cell (column-major scan, 120px spacing) not already occupied.
    occupied = {
        (row.posx, row.posy)
        for row in (
            await db.execute(
                select(Membership.posx, Membership.posy).where(
                    Membership.workspace_id == workspace_id,
                    Membership.deleted_at.is_(None),
                )
            )
        ).all()
    }
    posx, posy = 0, 0
    found = False
    for row in range(40):
        for col in range(40):
            candidate = (col * 120, row * 120)
            if candidate not in occupied:
                posx, posy = candidate
                found = True
                break
        if found:
            break
    membership = Membership(
        workspace_id=workspace_id,
        instance_id=instance.id,
        user_id=None,
        posx=posx,
        posy=posy,
    )
    db.add(membership)

    await emit(
        INSTANCE_CREATED,
        actor_type="user",
        actor_id=actor_id,
        resource_type="instance",
        resource_id=instance.id,
        payload={"workspace_path": resolved_path, "workspace_id": workspace_id},
        session=db,
    )
    if consistency_warning is not None:
        await emit(
            INSTANCE_KNOWLEDGE_INCONSISTENT,
            actor_type="user",
            actor_id=actor_id,
            resource_type="instance",
            resource_id=instance.id,
            payload={**consistency_warning, "entity_id": entity.id},
            session=db,
        )

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        code, message_key, message = conflict_error or _CONFLICT_ALREADY_INTRODUCED
        raise ConflictError(code, message_key, message)
    await db.refresh(instance)
    return instance, membership, consistency_warning
