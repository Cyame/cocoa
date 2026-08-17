"""Message delivery router — fire-and-forget delivery with passage gating.

Routes a parsed directive to eligible recipient entities within an workspace.

Delivery requires an active Passage edge (duplex: either orientation counts).
User → Lost One without a passage is **not** proxied to the instance; the
utterance is handed to the Workspace 小脑 (cerebellum) template reply +
notify-only collaboration job (V47-2 / V47-8).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_types import MESSAGING_DELIVERY_BLOCKED, MESSAGING_MESSAGE_SENT
from app.core.events import emit
from app.core.inject_queue import enqueue_inject
from app.core.passages import find_active_passage_between
from app.models.entity import Entity
from app.models.instance import Instance, InstanceStatus
from app.models.loop_state import InstanceLoopState, LoopStatus
from app.models.workspace import Membership
from app.schemas.internal import DeliveryMode
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


async def _delivery_mode_for_instance(
    session: AsyncSession, instance_id: str
) -> DeliveryMode:
    """V47-1 default: loop ``running`` → soft_inject; idle/missing → wake."""
    result = await session.execute(
        select(InstanceLoopState).where(
            InstanceLoopState.instance_id == instance_id,
            InstanceLoopState.deleted_at.is_(None),
        )
    )
    state = result.scalar_one_or_none()
    if state is not None and state.loop_status == LoopStatus.running.value:
        return "soft_inject"
    return "wake"


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
    """Persist the utterance + template reply; do not proxy to the Lost One Host."""
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
    # V47-8 template reply: composer transcript stores plaintext (same as the
    # legacy stub and user messages), so no i18n message_key here; API-level
    # errors are the only surface that carries message_keys.
    template_reply = (
        f"@{directive.target_entity} 尚未连接通道，消息已转交小脑。"
        "请先在拓扑中连接通道后再试。"
    )
    await append_composer_message(
        session,
        workspace_id=workspace_id,
        role="assistant",
        content=template_reply,
        target_entity=directive.target_entity,
        instance_id=instance_id,
        status="completed",
    )
    # V47-2: cerebellum collaboration job is notify-only — no wake, no new turn.
    if instance_id is not None:  # route_message only reaches here with an active instance
        await enqueue_inject(
            session,
            instance_id=instance_id,
            kind="cerebellum_route",
            delivery_mode="notify",
            payload={
                "text": text,
                "target_entity": directive.target_entity,
                "from_membership_id": from_membership_id,
            },
            tldr=text[:200],
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

        passage = await find_active_passage_between(
            session,
            workspace_id,
            from_membership_id,
            to_membership.id,
        )

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
        # V47-1: Passage success → collab downlink, mode derived from loop state.
        turn_text = _turn_text_for_directive(directive, general_text)
        delivery_mode = await _delivery_mode_for_instance(session, instance.id)
        await enqueue_inject(
            session,
            instance_id=instance.id,
            kind="collab_inject",
            delivery_mode=delivery_mode,
            payload={
                "target_entity": directive.target_entity,
                "cmd": directive.cmd,
                "args": directive.args,
                "text": turn_text,
                "passage_id": passage.id,
            },
            tldr=turn_text[:200],
        )
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
