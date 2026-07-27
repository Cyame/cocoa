"""Live-status endpoint for an office's topology nodes."""

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
from app.core.permissions import require_office_role
from app.models.loop_state import InstanceLoopState
from app.models.office import Membership
from app.schemas.glow import GlowColorOut, LiveStatusItemOut

router = APIRouter(prefix="/offices", tags=["Offices"])
add_error_responses(router)


_STATIC_FALLBACK: GlowColor = GlowColor("#94a3b8", GlowIntensity.static)


def _glow_to_out(glow: GlowColor) -> GlowColorOut:
    return GlowColorOut(color=glow.color, intensity=glow.intensity.value)


@router.get("/{office_id}/live-status", response_model=list[LiveStatusItemOut])
async def get_office_live_status(
    office_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> list[LiveStatusItemOut]:
    """Aggregate per-node glow state for the topology canvas."""
    await require_office_role(db, current_user.user_id, office_id, "viewer")

    memberships = (
        await db.execute(
            select(Membership)
            .where(
                Membership.office_id == office_id,
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

    items: list[LiveStatusItemOut] = []
    for membership in memberships:
        if membership.user_id is not None:
            glow = _glow_to_out(user_membership_glow())
            node_type: str = "user"
        else:
            state = loop_states_by_instance.get(membership.instance_id or "")
            glow = (
                _glow_to_out(loop_status_to_glow(state.loop_status))
                if state is not None
                else _glow_to_out(_STATIC_FALLBACK)
            )
            node_type = "instance"

        items.append(
            LiveStatusItemOut(
                membership_id=membership.id,
                posx=membership.posx,
                posy=membership.posy,
                node_type=node_type,
                glow=glow,
            )
        )

    return items
