"""v4.7 cerebellum template + Passage collab downlink tests.

Covers the V47-1 delivery-mode derivation table (Passage success: loop
``running`` → ``soft_inject``, ``idle``/missing → ``wake``) and the V47-3
rule (non-user sender without Passage keeps the ``not_neighbor`` block —
no cerebellum widening, no enqueue). The no-passage human template reply +
``cerebellum_route`` notify row lives in ``test_prd_v3_4_1_composer.py``.

Every DB-touching test uses the conftest per-test cloned database — never
``cocoa_dev``.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.event_types import HARNESS_INJECT_REQUESTED, MESSAGING_MESSAGE_SENT
from app.models.composer_message import ComposerMessage
from app.models.event import Event
from app.models.inject_queue import InstanceInjectQueue
from app.models.instance import InstanceStatus
from app.models.loop_state import InstanceLoopState, LoopStatus
from app.models.user import User
from app.models.workspace import Membership, Passage
from app.schemas.slash import Directive


async def _seed_scenario(
    session,
    *,
    workspace_factory,
    entity_factory,
    instance_factory,
    slug: str,
    with_passage: bool = False,
    loop_status: str | None = None,
    sender_is_user: bool = True,
):
    """Seed workspace + entity + instances + memberships (+passage/loop row)."""
    user = None
    if sender_is_user:
        user = User(
            username=f"u-{uuid4().hex[:8]}",
            email=f"{uuid4().hex[:8]}@example.com",
            password_hash="x",
        )
        session.add(user)
        await session.flush()

    workspace = await workspace_factory()
    entity = await entity_factory(slug=slug, namespace_id=workspace.namespace_id)
    instance = await instance_factory(
        entity_id=entity.id,
        workspace_id=workspace.id,
        status=InstanceStatus.running.value,
    )
    if not sender_is_user:
        sender_entity = await entity_factory(
            slug=f"sender-{uuid4().hex[:6]}",
            namespace_id=workspace.namespace_id,
        )
        sender_instance = await instance_factory(
            entity_id=sender_entity.id,
            workspace_id=workspace.id,
            status=InstanceStatus.running.value,
        )
        sender = Membership(
            workspace_id=workspace.id,
            user_id=None,
            instance_id=sender_instance.id,
            posx=0,
            posy=0,
        )
    else:
        sender = Membership(
            workspace_id=workspace.id,
            user_id=user.id if user else None,
            instance_id=None,
            posx=0,
            posy=0,
        )
    inst_mem = Membership(
        workspace_id=workspace.id,
        user_id=None,
        instance_id=instance.id,
        posx=120,
        posy=0,
    )
    session.add_all([sender, inst_mem])
    await session.flush()
    if with_passage:
        session.add(
            Passage(
                workspace_id=workspace.id,
                from_membership_id=sender.id,
                to_membership_id=inst_mem.id,
                is_active=True,
            )
        )
        await session.flush()
    if loop_status is not None:
        session.add(
            InstanceLoopState(instance_id=instance.id, loop_status=loop_status)
        )
        await session.flush()
    return workspace, entity, instance, sender, inst_mem


@pytest.mark.parametrize(
    ("loop_status", "expected_mode"),
    [
        (LoopStatus.running.value, "soft_inject"),
        (LoopStatus.idle.value, "wake"),
        (None, "wake"),
    ],
)
@pytest.mark.asyncio
async def test_passage_success_enqueues_collab_downlink_by_loop_status(
    session,
    workspace_factory,
    entity_factory,
    instance_factory,
    monkeypatch: pytest.MonkeyPatch,
    loop_status: str | None,
    expected_mode: str,
) -> None:
    """V47-1: Passage success enqueues collab_inject; mode follows loop state."""
    from app.core.message_router import route_message

    emitted: list[dict] = []

    async def fake_emit(event_type, **kwargs):
        emitted.append({"event_type": event_type, **kwargs})

    monkeypatch.setattr("app.core.message_router.emit", fake_emit)

    scheduled: list[dict] = []

    async def fake_schedule(**kwargs):
        scheduled.append(kwargs)
        return "turn-v47"

    monkeypatch.setattr(
        "app.core.composer_turns.schedule_user_turn",
        fake_schedule,
    )

    workspace, _, instance, sender, inst_mem = await _seed_scenario(
        session,
        workspace_factory=workspace_factory,
        entity_factory=entity_factory,
        instance_factory=instance_factory,
        slug="v47-passage",
        with_passage=True,
        loop_status=loop_status,
    )

    results = await route_message(
        session,
        from_membership_id=sender.id,
        workspace_id=workspace.id,
        directive=Directive(target_entity="v47-passage", cmd="", args=["你好"]),
        general_text=None,
    )

    assert len(results) == 1
    assert results[0].delivered is True
    assert results[0].turn_id == "turn-v47"
    assert scheduled and scheduled[0]["text"] == "你好"

    # messaging.message_sent audit event preserved (with passage_id).
    sent = [c for c in emitted if c["event_type"] == MESSAGING_MESSAGE_SENT]
    assert len(sent) == 1
    assert sent[0]["payload"]["passage_id"] is not None
    assert sent[0]["payload"]["instance_id"] == instance.id

    # Collab downlink row appended with the derived delivery mode.
    rows = (
        await session.execute(
            select(InstanceInjectQueue).where(
                InstanceInjectQueue.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].kind == "collab_inject"
    assert rows[0].delivery_mode == expected_mode
    assert rows[0].instance_id == instance.id
    assert rows[0].payload == {
        "target_entity": "v47-passage",
        "cmd": "",
        "args": ["你好"],
        "text": "你好",
        "passage_id": (
            await session.execute(
                select(Passage).where(
                    Passage.deleted_at.is_(None),
                    Passage.workspace_id == workspace.id,
                )
            )
        ).scalar_one().id,
    }
    # tldr is not a queue column; it surfaces on the inject_requested event.
    requested = (
        await session.execute(
            select(Event).where(Event.type == HARNESS_INJECT_REQUESTED)
        )
    ).scalar_one()
    assert requested.payload["queue_id"] == rows[0].id
    assert requested.payload["kind"] == "collab_inject"
    assert requested.payload["delivery_mode"] == expected_mode
    assert requested.payload["tldr"] == "你好"


@pytest.mark.asyncio
async def test_non_user_sender_without_passage_stays_blocked(
    session,
    workspace_factory,
    entity_factory,
    instance_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """V47-3: non-user sender without Passage keeps not_neighbor; no enqueue."""
    from app.core.message_router import route_message

    emitted: list[dict] = []

    async def fake_emit(event_type, **kwargs):
        emitted.append({"event_type": event_type, **kwargs})

    monkeypatch.setattr("app.core.message_router.emit", fake_emit)

    workspace, _, instance, sender, _ = await _seed_scenario(
        session,
        workspace_factory=workspace_factory,
        entity_factory=entity_factory,
        instance_factory=instance_factory,
        slug="v47-agent",
        sender_is_user=False,
    )

    results = await route_message(
        session,
        from_membership_id=sender.id,
        workspace_id=workspace.id,
        directive=Directive(target_entity="v47-agent", cmd="", args=["ping"]),
        general_text=None,
    )

    assert len(results) == 1
    assert results[0].delivered is False
    assert results[0].reason == "not_neighbor"
    assert results[0].instance_id == instance.id

    rows = (
        await session.execute(
            select(InstanceInjectQueue).where(
                InstanceInjectQueue.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    assert rows == []

    msgs = (
        await session.execute(
            select(ComposerMessage).where(
                ComposerMessage.workspace_id == workspace.id,
                ComposerMessage.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    assert msgs == []
