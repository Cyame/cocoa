"""Live-status endpoint for an workspace's topology nodes."""

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DB, CurrentUserDep, XOrgIdHeader
from app.core.avatar_status import compute_avatar_display_status
from app.core.composer_turns import instance_has_active_turn
from app.core.glow import (
    GlowColor,
    GlowIntensity,
    avatar_display_status_to_glow,
    user_membership_glow,
)
from app.core.migration_hash import compute_entity_migration_hash
from app.core.openapi import add_error_responses
from app.core.permissions import require_workspace_permission
from app.models.entity import Entity
from app.models.instance import Instance
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
    x_organization_id: XOrgIdHeader = None,
) -> list[LiveStatusItemOut]:
    """Aggregate per-node glow state for the topology canvas.

    Phase-15f T4: each instance node also carries ``outdated`` and
    ``active_hash`` fields. ``outdated`` is true when the running
    instance's ``active_hash`` does not match the current
    ``Entity.migration_hash`` (or the instance has no
    ``active_hash`` yet — first-time spawn caveat).
    """
    await require_workspace_permission(
        db,
        current_user.user_id,
        workspace_id,
        "can_view_workspace",
        x_organization_id=x_organization_id,
    )

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

    instance_ids = [m.instance_id for m in memberships if m.instance_id]
    # Phase-15f: join instances with their entities to expose
    # active_hash + outdated (compare to migration_hash or computed hash).
    instance_by_id: dict[str, Instance] = {}
    entity_by_id: dict[str, Entity] = {}
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

        if instance_by_id:
            emp_rows = (
                await db.execute(
                    select(Entity).where(
                        Entity.id.in_(
                            inst.entity_id for inst in instance_by_id.values()
                        ),
                        Entity.deleted_at.is_(None),
                    )
                )
            ).scalars().all()
            entity_by_id = {e.id: e for e in emp_rows}

    items: list[LiveStatusItemOut] = []
    for membership in memberships:
        if membership.user_id is not None:
            glow = _glow_to_out(user_membership_glow())
            node_type: str = "user"
            outdated = False
            active_hash: str | None = None
            instance_status: str | None = None
            mentionable = False
            display_status: str | None = None
        else:
            instance_id = membership.instance_id or ""
            instance = instance_by_id.get(instance_id)
            instance_status = instance.status if instance is not None else None
            in_conversation = (
                instance_has_active_turn(instance_id) if instance_id else False
            )
            display_status = (
                compute_avatar_display_status(
                    instance_status or "", in_conversation=in_conversation
                )
                if instance_status is not None
                else None
            )
            # @ only when avatar is up (running) — busy or idle both OK.
            mentionable = instance_status == "running"
            glow = _glow_to_out(
                avatar_display_status_to_glow(display_status or "stopped")
            )
            node_type = "instance"
            active_hash = instance.active_hash if instance is not None else None
            entity = (
                entity_by_id.get(instance.entity_id) if instance is not None else None
            )
            if entity is None:
                outdated = True
            else:
                expected_hash = entity.migration_hash or await compute_entity_migration_hash(
                    db, entity
                )
                outdated = active_hash is None or active_hash != expected_hash

        items.append(
            LiveStatusItemOut(
                membership_id=membership.id,
                posx=membership.posx,
                posy=membership.posy,
                node_type=node_type,
                glow=glow,
                outdated=outdated,
                active_hash=active_hash,
                instance_status=instance_status,
                mentionable=mentionable,
                display_status=display_status,
            )
        )

    return items
