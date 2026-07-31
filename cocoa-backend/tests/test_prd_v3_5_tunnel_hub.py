"""PRD-v3.5 Tunnel hub: auth, chat downlink, chunk ingest, kick old connection."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketState

from app.core.composer_turns import ComposerTurnState, get_turn, ingest_tunnel_chat_frame
from app.core.event_types import CHAT_RESPONSE_CHUNK, CHAT_RESPONSE_DONE
from app.services.tunnel.protocol import TunnelMessage, TunnelMessageType
from app.services.tunnel.tunnel_hub import TunnelHub, ingest_host_frame, tunnel_hub


@pytest.fixture(autouse=True)
def _clear_tunnel_hub():
    tunnel_hub._connections.clear()
    yield
    tunnel_hub._connections.clear()


def _mock_ws() -> MagicMock:
    ws = MagicMock()
    ws.client_state = WebSocketState.CONNECTED
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_auth_ok_and_is_connected(instance_factory, client: TestClient, session):
    inst = await instance_factory(proxy_token="tok-ok")
    await session.commit()

    with client.websocket_connect("/api/v1/tunnel/connect") as ws:
        ws.send_json(
            {
                "id": str(uuid4()),
                "type": "auth",
                "payload": {"instance_id": inst.id, "proxy_token": "tok-ok"},
                "ts": 1,
            }
        )
        reply = ws.receive_json()
        assert reply["type"] == "auth.ok"
        assert tunnel_hub.is_connected(inst.id)


@pytest.mark.asyncio
async def test_auth_rejects_bad_token(instance_factory, client: TestClient, session):
    inst = await instance_factory(proxy_token="tok-ok")
    await session.commit()

    with client.websocket_connect("/api/v1/tunnel/connect") as ws:
        ws.send_json(
            {
                "id": str(uuid4()),
                "type": "auth",
                "payload": {"instance_id": inst.id, "proxy_token": "wrong"},
                "ts": 1,
            }
        )
        reply = ws.receive_json()
        assert reply["type"] == "auth.error"
        assert not tunnel_hub.is_connected(inst.id)


@pytest.mark.asyncio
async def test_send_chat_request_downlink():
    hub = TunnelHub()
    ws = _mock_ws()
    iid = str(uuid4())
    await hub.register(iid, ws)
    ok = await hub.send_chat_request(
        instance_id=iid,
        turn_id="turn-1",
        text="hello",
        target_entity="alice",
        workspace_id="ws-1",
    )
    assert ok is True
    sent = ws.send_json.await_args.args[0]
    assert sent["type"] == TunnelMessageType.CHAT_REQUEST.value
    assert sent["turn_id"] == "turn-1"
    assert sent["payload"]["text"] == "hello"


@pytest.mark.asyncio
async def test_chunk_ingest_into_turn_queue():
    turn_id = str(uuid4())
    state = ComposerTurnState(
        turn_id=turn_id,
        instance_id="inst-1",
        workspace_id="ws-1",
        target_entity="alice",
        via_tunnel=True,
    )
    from app.core import composer_turns as ct

    ct._TURNS[turn_id] = state
    try:
        await ingest_tunnel_chat_frame(
            turn_id,
            {
                "type": CHAT_RESPONSE_CHUNK,
                "token": "Hi",
                "status": "responding",
            },
        )
        frame = await asyncio.wait_for(state.queue.get(), timeout=1)
        assert frame["type"] == CHAT_RESPONSE_CHUNK
        assert frame["token"] == "Hi"

        await ingest_tunnel_chat_frame(
            turn_id,
            {"type": CHAT_RESPONSE_DONE, "finish_reason": "stop", "status": "completed"},
        )
        done = await asyncio.wait_for(state.queue.get(), timeout=1)
        assert done["type"] == CHAT_RESPONSE_DONE
        sentinel = await asyncio.wait_for(state.queue.get(), timeout=1)
        assert sentinel is None
        assert get_turn(turn_id).status == "completed"
    finally:
        ct._TURNS.pop(turn_id, None)


@pytest.mark.asyncio
async def test_kick_old_connection():
    hub = TunnelHub()
    iid = str(uuid4())
    old = _mock_ws()
    new = _mock_ws()
    await hub.register(iid, old)
    await hub.register(iid, new)
    old.close.assert_awaited()
    assert hub._connections[iid].websocket is new


@pytest.mark.asyncio
async def test_schedule_user_turn_prefers_tunnel(monkeypatch):
    from app.core import composer_turns as ct

    sent: list[dict[str, Any]] = []

    class FakeHub:
        def is_connected(self, instance_id: str) -> bool:
            return True

        async def send_chat_request(self, **kwargs):
            sent.append(kwargs)
            return True

    monkeypatch.setattr(
        "app.services.tunnel.tunnel_hub.tunnel_hub",
        FakeHub(),
        raising=True,
    )

    async def fake_emit(*_a, **_k):
        return None

    monkeypatch.setattr(ct, "emit", fake_emit)

    session = AsyncMock()
    turn_id = await ct.schedule_user_turn(
        session=session,
        workspace_id="ws",
        instance_id="inst",
        target_entity="e",
        text="你好",
        cmd=None,
        from_membership_id="m1",
    )
    assert sent and sent[0]["text"] == "你好"
    assert sent[0]["turn_id"] == turn_id
    assert ct.get_turn(turn_id).via_tunnel is True
    ct._TURNS.pop(turn_id, None)


@pytest.mark.asyncio
async def test_ingest_host_frame_routes_to_composer(monkeypatch):
    seen: list[tuple[str, dict]] = []

    async def fake_ingest(turn_id: str, frame: dict):
        seen.append((turn_id, frame))

    monkeypatch.setattr(
        "app.core.composer_turns.ingest_tunnel_chat_frame", fake_ingest
    )
    msg = TunnelMessage(
        type=TunnelMessageType.CHAT_RESPONSE_CHUNK.value,
        turn_id="t1",
        payload={"token": "x", "turn_id": "t1"},
    )
    await ingest_host_frame("inst", msg)
    assert seen == [("t1", {
        "type": "chat.response.chunk",
        "turn_id": "t1",
        "instance_id": "inst",
        "token": "x",
    })]
