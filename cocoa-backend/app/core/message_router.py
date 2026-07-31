"""Message delivery router — fire-and-forget delivery with passage gating.

Routes a parsed directive to eligible recipient entities within an workspace.
Delivery only succeeds when an active Passage edge exists from the sender's
membership to the target instance's membership (passage gating).

Fire-and-forget: message content is NOT persisted to the database.  Only
audit events (messaging.message_sent / messaging.delivery_blocked) are
emitted for observability.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_types import MESSAGING_DELIVERY_BLOCKED, MESSAGING_MESSAGE_SENT
from app.core.events import emit
from app.models.entity import Entity
from app.models.instance import Instance, InstanceStatus
from app.models.workspace import Passage, Membership
from app.schemas.slash import Directive

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class MessageDeliveryResult:
    """Outcome of attempting to deliver a message to one target instance.

    Attributes:
        target_entity: Entity slug the directive was addressed to.
        delivered: Whether the message passed passage gating.
        reason: Machine-readable failure code when ``delivered`` is False.
            Possible values: ``"entity_not_found"``,
            ``"no_active_instance"``, ``"not_neighbor"``.
        instance_id: UUID of the target :class:`~app.models.instance.Instance`
            (populated for gating-attempt results, ``None`` for early-out
            rejections like ``entity_not_found``).
        turn_id: Composer turn id when a user_turn stream was scheduled.
    """

    target_entity: str
    delivered: bool
    reason: str | None = None
    instance_id: str | None = None
    turn_id: str | None = None


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


async def route_message(
    session: AsyncSession,
    from_membership_id: str,
    workspace_id: str,
    directive: Directive,
    general_text: str | None = None,
) -> list[MessageDeliveryResult]:
    """Attempt to deliver *directive* to eligible recipients in an workspace.

    Delivery is gated by the passage graph: a message is only delivered
    to a target instance when an active :class:`~app.models.workspace.Passage`
    edge exists from *from_membership_id* to the target instance's membership.

    Parameters
    ----------
    session:
        Active async database session.  The caller owns the transaction
        boundary — this function never commits.
    from_membership_id:
        UUID of the sender's :class:`~app.models.workspace.Membership`.
    workspace_id:
        UUID of the workspace where delivery occurs.
    directive:
        Parsed directive.  ``target_entity`` identifies the recipient;
        a bare ``/cmd`` with ``target_entity=None`` is silently skipped.
    general_text:
        Optional free-form text accompanying the directive.  Included in
        success audit payloads but never persisted as message content.

    Returns
    -------
    list[MessageDeliveryResult]
        One result per target instance that was attempted.  Empty list when
        ``directive.target_entity`` is ``None``.
    """
    # ---- bare /cmd (no target) -----------------------------------------
    if directive.target_entity is None:
        return []

    # ---- resolve target entity ---------------------------------------
    result = await session.execute(
        select(Entity).where(
            Entity.slug == directive.target_entity,
            Entity.deleted_at.is_(None),
        )
    )
    entity = result.scalar_one_or_none()
    if entity is None:
        return [
            MessageDeliveryResult(
                target_entity=directive.target_entity,
                delivered=False,
                reason="entity_not_found",
            )
        ]

    # ---- resolve active instances in this workspace -----------------------
    result = await session.execute(
        select(Instance).where(
            Instance.entity_id == entity.id,
            Instance.workspace_id == workspace_id,
            Instance.status.in_(
                [
                    InstanceStatus.running,
                    InstanceStatus.pending,
                    InstanceStatus.creating,
                    InstanceStatus.deploying,
                ]
            ),
            Instance.deleted_at.is_(None),
        )
    )
    instances = result.scalars().all()
    if not instances:
        return [
            MessageDeliveryResult(
                target_entity=directive.target_entity,
                delivered=False,
                reason="no_active_instance",
            )
        ]

    # ---- per-instance passage gate ------------------------------------
    results: list[MessageDeliveryResult] = []

    for instance in instances:
        # --- resolve target membership ---
        result = await session.execute(
            select(Membership).where(
                Membership.instance_id == instance.id,
                Membership.workspace_id == workspace_id,
                Membership.deleted_at.is_(None),
            )
        )
        to_membership = result.scalar_one_or_none()
        if to_membership is None:
            # Instance exists but has no membership — treat as not neighbor
            await emit(
                MESSAGING_DELIVERY_BLOCKED,
                actor_type="membership",
                actor_id=from_membership_id,
                resource_type="instance",
                resource_id=instance.id,
                payload={
                    "target_entity": directive.target_entity,
                    "cmd": directive.cmd,
                    "workspace_id": workspace_id,
                    "instance_id": instance.id,
                    "reason_detail": "target_membership_missing",
                },
                session=session,
            )
            results.append(
                MessageDeliveryResult(
                    target_entity=directive.target_entity,
                    delivered=False,
                    reason="not_neighbor",
                    instance_id=instance.id,
                )
            )
            continue

        # --- check passage edge ---
        result = await session.execute(
            select(Passage).where(
                Passage.workspace_id == workspace_id,
                Passage.from_membership_id == from_membership_id,
                Passage.to_membership_id == to_membership.id,
                Passage.is_active,
                Passage.deleted_at.is_(None),
            )
        )
        passage = result.scalar_one_or_none()

        if passage is None:
            # No active passage → delivery blocked
            await emit(
                MESSAGING_DELIVERY_BLOCKED,
                actor_type="membership",
                actor_id=from_membership_id,
                resource_type="membership",
                resource_id=to_membership.id,
                payload={
                    "target_entity": directive.target_entity,
                    "cmd": directive.cmd,
                    "workspace_id": workspace_id,
                    "instance_id": instance.id,
                    "to_membership_id": to_membership.id,
                },
                session=session,
            )
            results.append(
                MessageDeliveryResult(
                    target_entity=directive.target_entity,
                    delivered=False,
                    reason="not_neighbor",
                    instance_id=instance.id,
                )
            )
        else:
            # Active passage present → deliver
            await emit(
                MESSAGING_MESSAGE_SENT,
                actor_type="membership",
                actor_id=from_membership_id,
                resource_type="instance",
                resource_id=instance.id,
                payload={
                    "target_entity": directive.target_entity,
                    "cmd": directive.cmd,
                    "args": directive.args,
                    "workspace_id": workspace_id,
                    "instance_id": instance.id,
                    "to_membership_id": to_membership.id,
                    "passage_id": passage.id,
                    "general_text": general_text,
                },
                session=session,
            )
            # Chat mention: args hold the utterance after @slug.
            # Slash directive: prefer general_text, else args joined.
            if directive.cmd:
                turn_text = (general_text or "").strip()
                if not turn_text:
                    turn_text = " ".join(directive.args).strip()
                if not turn_text:
                    turn_text = directive.cmd
            else:
                turn_text = " ".join(directive.args).strip()
                if not turn_text:
                    turn_text = (general_text or "").strip()
            from app.core.composer_turns import schedule_user_turn

            turn_id = await schedule_user_turn(
                session=session,
                workspace_id=workspace_id,
                instance_id=instance.id,
                target_entity=directive.target_entity,
                text=turn_text,
                cmd=directive.cmd or None,
                from_membership_id=from_membership_id,
            )
            results.append(
                MessageDeliveryResult(
                    target_entity=directive.target_entity,
                    delivered=True,
                    instance_id=instance.id,
                    turn_id=turn_id,
                )
            )

    return results
