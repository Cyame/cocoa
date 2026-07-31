"""Message delivery router — fire-and-forget delivery with passage gating.

Routes a parsed directive to eligible recipient entities within an workspace.

Delivery requires an active Passage edge. User → Lost One without a passage
is **not** proxied to the instance; the utterance is handed to the Workspace
小脑 (cerebellum) stub for later business logic.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_types import MESSAGING_DELIVERY_BLOCKED, MESSAGING_MESSAGE_SENT
from app.core.events import emit
from app.models.entity import Entity
from app.models.instance import Instance, InstanceStatus
from app.models.workspace import Membership, Passage
from app.schemas.slash import Directive


@dataclass
class MessageDeliveryResult:
    """Outcome of attempting to deliver a message to one target instance."""

    target_entity: str
    delivered: bool
    reason: str | None = None
    instance_id: str | None = None
    turn_id: str | None = None


def _turn_text_for_directive(directive: Directive, general_text: str | None) -> str:
    if directive.cmd:
        turn_text = (general_text or "").strip()
        if not turn_text:
            turn_text = " ".join(directive.args).strip()
        if not turn_text:
            turn_text = directive.cmd
        return turn_text
    turn_text = " ".join(directive.args).strip()
    if not turn_text:
        turn_text = (general_text or "").strip()
    return turn_text


async def _route_to_cerebellum(
    session: AsyncSession,
    *,
    from_membership_id: str,
    workspace_id: str,
    directive: Directive,
    general_text: str | None,
    instance_id: str | None,
    to_membership_id: str | None,
    author_user_id: str | None,
) -> MessageDeliveryResult:
    """Persist the utterance + stub reply; do not proxy to the Lost One Host."""
    from app.services.composer_transcript import append_composer_message

    text = _turn_text_for_directive(directive, general_text)
    await emit(
        MESSAGING_DELIVERY_BLOCKED,
        actor_type="membership",
        actor_id=from_membership_id,
        resource_type="instance" if instance_id else "workspace",
        resource_id=instance_id or workspace_id,
        payload={
            "target_entity": directive.target_entity,
            "cmd": directive.cmd,
            "workspace_id": workspace_id,
            "instance_id": instance_id,
            "to_membership_id": to_membership_id,
            "reason_detail": "routed_to_cerebellum",
            "text": text,
        },
        session=session,
    )
    await append_composer_message(
        session,
        workspace_id=workspace_id,
        role="user",
        content=text,
        target_entity=directive.target_entity,
        instance_id=instance_id,
        status="completed",
        author_user_id=author_user_id,
    )
    await append_composer_message(
        session,
        workspace_id=workspace_id,
        role="system",
        content=(
            f"@{directive.target_entity} is not connected via passage; "
            "message routed to Workspace cerebellum (stub)."
        ),
        target_entity=directive.target_entity,
        instance_id=instance_id,
        status="completed",
    )
    return MessageDeliveryResult(
        target_entity=directive.target_entity or "",
        delivered=False,
        reason="routed_to_cerebellum",
        instance_id=instance_id,
    )


async def route_message(
    session: AsyncSession,
    from_membership_id: str,
    workspace_id: str,
    directive: Directive,
    general_text: str | None = None,
) -> list[MessageDeliveryResult]:
    """Attempt to deliver *directive* to eligible recipients in an workspace."""
    if directive.target_entity is None:
        return []

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

    sender = await session.get(Membership, from_membership_id)
    sender_is_user = (
        sender is not None
        and sender.deleted_at is None
        and sender.user_id is not None
    )
    author_user_id = sender.user_id if sender_is_user and sender is not None else None

    results: list[MessageDeliveryResult] = []
    for instance in instances:
        result = await session.execute(
            select(Membership).where(
                Membership.instance_id == instance.id,
                Membership.workspace_id == workspace_id,
                Membership.deleted_at.is_(None),
            )
        )
        to_membership = result.scalar_one_or_none()
        if to_membership is None:
            if sender_is_user:
                results.append(
                    await _route_to_cerebellum(
                        session,
                        from_membership_id=from_membership_id,
                        workspace_id=workspace_id,
                        directive=directive,
                        general_text=general_text,
                        instance_id=instance.id,
                        to_membership_id=None,
                        author_user_id=author_user_id,
                    )
                )
            else:
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

        result = await session.execute(
            select(Passage).where(
                Passage.workspace_id == workspace_id,
                Passage.from_membership_id == from_membership_id,
                Passage.to_membership_id == to_membership.id,
                Passage.is_active.is_(True),
                Passage.deleted_at.is_(None),
            )
        )
        passage = result.scalar_one_or_none()

        if passage is None:
            if sender_is_user:
                results.append(
                    await _route_to_cerebellum(
                        session,
                        from_membership_id=from_membership_id,
                        workspace_id=workspace_id,
                        directive=directive,
                        general_text=general_text,
                        instance_id=instance.id,
                        to_membership_id=to_membership.id,
                        author_user_id=author_user_id,
                    )
                )
            else:
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
            continue

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
        from app.core.composer_turns import schedule_user_turn

        turn_id = await schedule_user_turn(
            session=session,
            workspace_id=workspace_id,
            instance_id=instance.id,
            target_entity=directive.target_entity,
            text=_turn_text_for_directive(directive, general_text),
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
