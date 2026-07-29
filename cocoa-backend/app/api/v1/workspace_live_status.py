"""Live-status endpoint for an workspace's topology nodes."""

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DB, CurrentUserDep
from app.core.glow import (
    GlowColor,
    GlowIntensity,
    loop_status_to_glow,
    user_membership_glow,
)
from app.core.openapi import add_error_responses
from app.core.permissions import require_workspace_role
from app.models.entity import Entity
from app.models.instance import Instance
from app.models.loop_state import InstanceLoopState
from app.models.workspace import Membership
from app.schemas.glow import GlowColorOut, LiveStatusItemOut

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])
add_error_responses(router)


_STATIC_FALLBACK: GlowColor = GlowColor("#94a3b8", GlowIntensity.static)


def _glow_to_out(glow: GlowColor) -> GlowColorOut:
    return GlowColorOut(color=glow.color, intensity=glow.intensity.value)


@router.get("/{workspace_id}/live-status", response_model=list[LiveStatusItemOut])
async def get_workspace_live_status(
    workspace_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> list[LiveStatusItemOut]:
    """Aggregate per-node glow state for the topology canvas.

    Phase-15f T4: each instance node also carries ``outdated`` and
    ``active_hash`` fields. ``outdated`` is true when the running
    instance's ``active_hash`` does not match the current
    ``Entity.migration_hash`` (or the instance has no
    ``active_hash`` yet — first-time spawn caveat).
    """
    await require_workspace_role(db, current_user.user_id, workspace_id, "viewer")

    memberships = (
        await db.execute(
            select(Membership)
            .where(
                Membership.workspace_id == workspace_id,
                Membership.deleted_at.is_(None),
            )
            .order_by(Membership.created_at)
        )
    ).scalars().all()

    loop_states_by_instance: dict[str, InstanceLoopState] = {}
    instance_ids = [m.instance_id for m in memberships if m.instance_id]
    if instance_ids:
        loop_state_rows = (
            await db.execute(
                select(InstanceLoopState).where(
                    InstanceLoopState.instance_id.in_(instance_ids),
                    InstanceLoopState.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        loop_states_by_instance = {row.instance_id: row for row in loop_state_rows}

    # Phase-15f: join instances with their entities to expose
    # active_hash + deprecated-by-promote flag.
    instance_by_id: dict[str, Instance] = {}
    entity_migration_hash: dict[str, str | None] = {}
    if instance_ids:
        inst_rows = (
            await db.execute(
                select(Instance).where(
                    Instance.id.in_(instance_ids),
                    Instance.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        instance_by_id = {row.id: row for row in inst_rows}

        emp_rows = (
            await db.execute(
                select(Entity.id, Entity.migration_hash).where(
                    Entity.id.in_(
                        inst.entity_id for inst in instance_by_id.values()
                    ),
                    Entity.deleted_at.is_(None),
                )
            )
        ).all()
        entity_migration_hash = {row[0]: row[1] for row in emp_rows}

    items: list[LiveStatusItemOut] = []
    for membership in memberships:
        if membership.user_id is not None:
            glow = _glow_to_out(user_membership_glow())
            node_type: str = "user"
            outdated = False
            active_hash: str | None = None
        else:
            instance_id = membership.instance_id or ""
            state = loop_states_by_instance.get(instance_id)
            glow = (
                _glow_to_out(loop_status_to_glow(state.loop_status))
                if state is not None
                else _glow_to_out(_STATIC_FALLBACK)
            )
            node_type = "instance"
            instance = instance_by_id.get(instance_id)
            active_hash = instance.active_hash if instance is not None else None
            expected_hash = (
                entity_migration_hash.get(instance.entity_id)
                if instance is not None
                else None
            )
            outdated = (
                active_hash is None
                or active_hash != expected_hash
            )

        items.append(
            LiveStatusItemOut(
                membership_id=membership.id,
                posx=membership.posx,
                posy=membership.posy,
                node_type=node_type,
                glow=glow,
                outdated=outdated,
                active_hash=active_hash,
            )
        )

    return items
