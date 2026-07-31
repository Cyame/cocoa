"""PRD-v3.4.1 composer turns + mention parse + passage gate."""

from __future__ import annotations

import pytest

from app.core.composer_turns import _iter_tokens, get_turn, schedule_user_turn
from app.core.slash_parser import parse_turn


@pytest.mark.asyncio
async def test_stub_token_stream_yields_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    tokens: list[str] = []
    finish = None
    async for chunk in _iter_tokens("ping"):
        if chunk.token:
            tokens.append(chunk.token)
        if chunk.finish_reason:
            finish = chunk.finish_reason
    assert "".join(tokens) == "[stub] ping"
    assert finish == "stop"


def test_parse_turn_multi_mention_chat() -> None:
    turn = parse_turn("@a 你好\n@b hello")
    assert len(turn.directives) == 2
    assert turn.directives[0].target_entity == "a"
    assert turn.directives[0].cmd == ""
    assert turn.directives[0].args == ["你好"]
    assert turn.directives[1].target_entity == "b"
    assert turn.directives[1].args == ["hello"]


def test_parse_turn_same_line_multi_mention_chat() -> None:
    """PRD-v3.4.1 / 14b: same-line @a … @b … expands to N chat directives."""
    turn = parse_turn("@a 你好 @b hello")
    assert len(turn.directives) == 2
    assert turn.directives[0].target_entity == "a"
    assert turn.directives[0].cmd == ""
    assert turn.directives[0].args == ["你好"]
    assert turn.directives[1].target_entity == "b"
    assert turn.directives[1].args == ["hello"]


def test_parse_turn_same_line_with_cmd_stays_single() -> None:
    """Slash commands keep single-directive semantics (no inline @ expand)."""
    turn = parse_turn("@a /status @b hello")
    assert len(turn.directives) == 1
    assert turn.directives[0].target_entity == "a"
    assert turn.directives[0].cmd == "/status"


@pytest.mark.asyncio
async def test_schedule_user_turn_registers_state(session) -> None:
    """schedule_user_turn creates in-memory turn + emits without requiring LLM key."""
    turn_id = await schedule_user_turn(
        session=session,
        workspace_id="ws-test",
        instance_id="inst-test",
        target_entity="alice",
        text="hi",
        cmd=None,
        from_membership_id="mem-test",
    )
    state = get_turn(turn_id)
    assert state is not None
    assert state.status == "responding"
    assert state.target_entity == "alice"


@pytest.mark.asyncio
async def test_user_without_passage_routes_to_cerebellum(
    session,
    workspace_factory,
    entity_factory,
    instance_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """User → Lost One without Passage must NOT proxy; routes to cerebellum stub."""
    from uuid import uuid4

    from sqlalchemy import select

    from app.core.message_router import route_message
    from app.models.composer_message import ComposerMessage
    from app.models.instance import InstanceStatus
    from app.models.user import User
    from app.models.workspace import Membership, MembershipRole, Passage
    from app.schemas.slash import Directive

    async def fake_emit(*_a, **_k):
        return None

    monkeypatch.setattr("app.core.message_router.emit", fake_emit)

    scheduled: list[dict] = []

    async def fake_schedule(**kwargs):
        scheduled.append(kwargs)
        return "should-not-run"

    monkeypatch.setattr(
        "app.core.composer_turns.schedule_user_turn",
        fake_schedule,
    )

    user = User(
        username=f"u-{uuid4().hex[:8]}",
        email=f"{uuid4().hex[:8]}@example.com",
        password_hash="x",
    )
    session.add(user)
    await session.flush()

    workspace = await workspace_factory()
    entity = await entity_factory(slug="ceshi", namespace_id=workspace.namespace_id)
    instance = await instance_factory(
        entity_id=entity.id,
        workspace_id=workspace.id,
        status=InstanceStatus.running.value,
    )
    user_mem = Membership(
        workspace_id=workspace.id,
        user_id=user.id,
        instance_id=None,
        posx=0,
        posy=0,
        role=MembershipRole.owner.value,
    )
    inst_mem = Membership(
        workspace_id=workspace.id,
        user_id=None,
        instance_id=instance.id,
        posx=120,
        posy=0,
        role=MembershipRole.viewer.value,
    )
    session.add_all([user_mem, inst_mem])
    await session.flush()

    results = await route_message(
        session,
        from_membership_id=user_mem.id,
        workspace_id=workspace.id,
        directive=Directive(target_entity="ceshi", cmd="", args=["你好"]),
        general_text=None,
    )
    assert len(results) == 1
    assert results[0].delivered is False
    assert results[0].reason == "routed_to_cerebellum"
    assert results[0].turn_id is None
    assert scheduled == []

    msgs = (
        await session.execute(
            select(ComposerMessage).where(
                ComposerMessage.workspace_id == workspace.id,
                ComposerMessage.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    roles = {m.role for m in msgs}
    assert "user" in roles
    assert "system" in roles

    passage = (
        await session.execute(
            select(Passage).where(
                Passage.from_membership_id == user_mem.id,
                Passage.to_membership_id == inst_mem.id,
                Passage.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    assert passage is None


@pytest.mark.asyncio
async def test_user_with_passage_proxies_to_instance(
    session,
    workspace_factory,
    entity_factory,
    instance_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from uuid import uuid4

    from app.core.message_router import route_message
    from app.models.instance import InstanceStatus
    from app.models.user import User
    from app.models.workspace import Membership, MembershipRole, Passage
    from app.schemas.slash import Directive

    async def fake_emit(*_a, **_k):
        return None

    monkeypatch.setattr("app.core.message_router.emit", fake_emit)

    scheduled: list[dict] = []

    async def fake_schedule(**kwargs):
        scheduled.append(kwargs)
        return "turn-ok"

    monkeypatch.setattr(
        "app.core.composer_turns.schedule_user_turn",
        fake_schedule,
    )

    user = User(
        username=f"u-{uuid4().hex[:8]}",
        email=f"{uuid4().hex[:8]}@example.com",
        password_hash="x",
    )
    session.add(user)
    await session.flush()

    workspace = await workspace_factory()
    entity = await entity_factory(slug="ceshi", namespace_id=workspace.namespace_id)
    instance = await instance_factory(
        entity_id=entity.id,
        workspace_id=workspace.id,
        status=InstanceStatus.running.value,
    )
    user_mem = Membership(
        workspace_id=workspace.id,
        user_id=user.id,
        instance_id=None,
        posx=0,
        posy=0,
        role=MembershipRole.owner.value,
    )
    inst_mem = Membership(
        workspace_id=workspace.id,
        user_id=None,
        instance_id=instance.id,
        posx=120,
        posy=0,
        role=MembershipRole.viewer.value,
    )
    session.add_all([user_mem, inst_mem])
    await session.flush()
    session.add(
        Passage(
            workspace_id=workspace.id,
            from_membership_id=user_mem.id,
            to_membership_id=inst_mem.id,
            is_active=True,
        )
    )
    await session.flush()

    results = await route_message(
        session,
        from_membership_id=user_mem.id,
        workspace_id=workspace.id,
        directive=Directive(target_entity="ceshi", cmd="", args=["你好"]),
        general_text=None,
    )
    assert len(results) == 1
    assert results[0].delivered is True
    assert results[0].turn_id == "turn-ok"
    assert scheduled and scheduled[0]["text"] == "你好"


@pytest.mark.asyncio
async def test_reverse_passage_still_proxies_to_instance(
    session,
    workspace_factory,
    entity_factory,
    instance_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Duplex lock: Lost One → User edge still counts for User → Lost One delivery."""
    from uuid import uuid4

    from app.core.message_router import route_message
    from app.models.instance import InstanceStatus
    from app.models.user import User
    from app.models.workspace import Membership, MembershipRole, Passage
    from app.schemas.slash import Directive

    async def fake_emit(*_a, **_k):
        return None

    monkeypatch.setattr("app.core.message_router.emit", fake_emit)

    scheduled: list[dict] = []

    async def fake_schedule(**kwargs):
        scheduled.append(kwargs)
        return "turn-rev"

    monkeypatch.setattr(
        "app.core.composer_turns.schedule_user_turn",
        fake_schedule,
    )

    user = User(
        username=f"u-{uuid4().hex[:8]}",
        email=f"{uuid4().hex[:8]}@example.com",
        password_hash="x",
    )
    session.add(user)
    await session.flush()

    workspace = await workspace_factory()
    entity = await entity_factory(slug="rev-ceshi", namespace_id=workspace.namespace_id)
    instance = await instance_factory(
        entity_id=entity.id,
        workspace_id=workspace.id,
        status=InstanceStatus.running.value,
    )
    user_mem = Membership(
        workspace_id=workspace.id,
        user_id=user.id,
        instance_id=None,
        posx=0,
        posy=0,
        role=MembershipRole.owner.value,
    )
    inst_mem = Membership(
        workspace_id=workspace.id,
        user_id=None,
        instance_id=instance.id,
        posx=120,
        posy=0,
        role=MembershipRole.viewer.value,
    )
    session.add_all([user_mem, inst_mem])
    await session.flush()
    # Reverse click-order orientation: Lost One → User
    session.add(
        Passage(
            workspace_id=workspace.id,
            from_membership_id=inst_mem.id,
            to_membership_id=user_mem.id,
            is_active=True,
        )
    )
    await session.flush()

    results = await route_message(
        session,
        from_membership_id=user_mem.id,
        workspace_id=workspace.id,
        directive=Directive(target_entity="rev-ceshi", cmd="", args=["ping"]),
        general_text=None,
    )
    assert len(results) == 1
    assert results[0].delivered is True
    assert results[0].turn_id == "turn-rev"
    assert scheduled
