"""Composer transcript persistence + DB filters."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.user import User
from app.models.workspace import Membership
from app.services.composer_transcript import append_composer_message, list_composer_messages


@pytest.mark.asyncio
async def test_enrich_prefers_display_name_and_assistant_recipient(
    session,
    workspace_factory,
    entity_factory,
) -> None:
    from app.services.composer_transcript import (
        append_composer_message,
        enrich_composer_message_items,
        list_composer_messages,
    )

    workspace = await workspace_factory()
    user = User(
        username=f"u-{uuid4().hex[:8]}",
        nickname="阿文",
        email=f"{uuid4().hex[:8]}@example.com",
        password_hash="x",
    )
    session.add(user)
    await session.flush()
    await entity_factory(
        namespace_id=workspace.namespace_id,
        slug="ceshi",
        name="ceshi-name",
        display_name="测试",
    )
    turn_id = str(uuid4())
    await append_composer_message(
        session,
        workspace_id=workspace.id,
        role="user",
        content="@ceshi hi",
        target_entity="ceshi",
        turn_id=turn_id,
        author_user_id=user.id,
    )
    await append_composer_message(
        session,
        workspace_id=workspace.id,
        role="assistant",
        content="reply",
        target_entity="ceshi",
        turn_id=turn_id,
    )
    await session.commit()

    rows = await list_composer_messages(session, workspace.id)
    items = await enrich_composer_message_items(session, rows)
    by_role = {i["role"]: i for i in items}
    assert by_role["user"]["target_entity_name"] == "测试"
    assert by_role["user"]["author_username"] == user.username
    assert by_role["user"]["author_nickname"] == "阿文"
    assert by_role["user"]["author_display_name"] == "阿文"
    assert by_role["assistant"]["target_entity_name"] == "测试"
    assert by_role["assistant"]["recipient_username"] == user.username
    assert by_role["assistant"]["recipient_display_name"] == "阿文"

@pytest.mark.asyncio
async def test_list_composer_messages_speaker_recipient_parties(
    session,
    workspace_factory,
) -> None:
    workspace = await workspace_factory()
    user = User(
        username=f"u-{uuid4().hex[:8]}",
        email=f"{uuid4().hex[:8]}@example.com",
        password_hash="x",
    )
    session.add(user)
    await session.flush()
    turn_id = str(uuid4())
    await append_composer_message(
        session,
        workspace_id=workspace.id,
        role="user",
        content="@alice hi",
        target_entity="alice",
        turn_id=turn_id,
        author_user_id=user.id,
    )
    await append_composer_message(
        session,
        workspace_id=workspace.id,
        role="assistant",
        content="hello",
        target_entity="alice",
        turn_id=turn_id,
    )
    await session.commit()

    as_speaker = await list_composer_messages(
        session, workspace.id, speaker=f"user:{user.username}"
    )
    assert len(as_speaker) == 1
    assert as_speaker[0].role == "user"

    entity_speaker = await list_composer_messages(
        session, workspace.id, speaker="entity:alice"
    )
    assert len(entity_speaker) == 1
    assert entity_speaker[0].role == "assistant"

    to_entity = await list_composer_messages(
        session, workspace.id, recipient="entity:alice"
    )
    assert len(to_entity) == 1
    assert to_entity[0].role == "user"

    to_user = await list_composer_messages(
        session, workspace.id, recipient=f"user:{user.username}"
    )
    assert len(to_user) == 1
    assert to_user[0].role == "assistant"


@pytest.mark.asyncio
async def test_list_composer_messages_filters_by_role_and_target(
    session,
    workspace_factory,
) -> None:
    workspace = await workspace_factory()
    user = User(
        username=f"u-{uuid4().hex[:8]}",
        email=f"{uuid4().hex[:8]}@example.com",
        password_hash="x",
    )
    session.add(user)
    await session.flush()

    await append_composer_message(
        session,
        workspace_id=workspace.id,
        role="user",
        content="@alice hi",
        target_entity="alice",
        author_user_id=user.id,
    )
    await append_composer_message(
        session,
        workspace_id=workspace.id,
        role="assistant",
        content="hello",
        target_entity="alice",
    )
    await append_composer_message(
        session,
        workspace_id=workspace.id,
        role="user",
        content="@bob hi",
        target_entity="bob",
        author_user_id=user.id,
    )
    await session.commit()

    only_alice = await list_composer_messages(
        session, workspace.id, target_entity="alice"
    )
    assert len(only_alice) == 2
    assert {m.target_entity for m in only_alice} == {"alice"}

    only_user = await list_composer_messages(session, workspace.id, role="user")
    assert len(only_user) == 2
    assert all(m.role == "user" for m in only_user)

    by_name = await list_composer_messages(
        session, workspace.id, author_username=user.username
    )
    assert len(by_name) == 2
    assert all(m.role == "user" for m in by_name)


@pytest.mark.asyncio
async def test_messaging_send_commits_composer_rows(
    client,
    session,
    workspace_factory,
    entity_factory,
    instance_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /messaging/messages must commit composer_messages (get_db does not)."""
    from app.core.security import create_access_token
    from app.models.instance import InstanceStatus

    async def fake_emit(*_a, **_k):
        return None

    monkeypatch.setattr("app.core.message_router.emit", fake_emit)

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
    )
    inst_mem = Membership(
        workspace_id=workspace.id,
        user_id=None,
        instance_id=instance.id,
        posx=120,
        posy=0,
    )
    session.add_all([user_mem, inst_mem])
    await session.commit()

    from app.core.config import settings

    token = create_access_token(user.id, False, settings.JWT_SECRET)
    resp = client.post(
        "/api/v1/messaging/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"workspace_id": workspace.id, "turn_text": "@ceshi 你好"},
    )
    assert resp.status_code == 200, resp.text

    listed = client.get(
        f"/api/v1/workspaces/{workspace.id}/composer/messages",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    roles = {m["role"] for m in items}
    assert "user" in roles
    assert "system" in roles or "assistant" in roles
    assert any("你好" in (m.get("content") or "") for m in items)
