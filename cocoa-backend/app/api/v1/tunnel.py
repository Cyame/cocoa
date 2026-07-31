"""Tunnel WebSocket endpoint — Instance Host outbound connection."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.db import get_session_factory
from app.models.instance import Instance
from app.services.tunnel.protocol import TunnelMessage, TunnelMessageType
from app.services.tunnel.tunnel_hub import (
    AUTH_TIMEOUT_S,
    PING_INTERVAL_S,
    ingest_host_frame,
    tunnel_hub,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Tunnel"])


@router.websocket("/tunnel/connect")
async def tunnel_connect(websocket: WebSocket) -> None:
    await websocket.accept()
    instance_id: str | None = None
    try:
        raw = await asyncio.wait_for(websocket.receive_json(), timeout=AUTH_TIMEOUT_S)
    except TimeoutError:
        await _safe_send(
            websocket,
            TunnelMessage(
                type=TunnelMessageType.AUTH_ERROR.value,
                payload={"reason": "auth_timeout"},
            ),
        )
        await websocket.close(code=4001, reason="auth_timeout")
        return
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001
        await websocket.close(code=4002, reason="bad_auth_frame")
        return

    msg = TunnelMessage.from_dict(raw if isinstance(raw, dict) else {})
    if msg.type != TunnelMessageType.AUTH.value:
        await _safe_send(
            websocket,
            TunnelMessage(
                type=TunnelMessageType.AUTH_ERROR.value,
                payload={"reason": "expected_auth"},
            ),
        )
        await websocket.close(code=4002, reason="expected_auth")
        return

    instance_id = str(msg.payload.get("instance_id") or "").strip()
    token = str(msg.payload.get("proxy_token") or msg.payload.get("token") or "").strip()
    if not instance_id or not token:
        await _safe_send(
            websocket,
            TunnelMessage(
                type=TunnelMessageType.AUTH_ERROR.value,
                payload={"reason": "missing_credentials"},
            ),
        )
        await websocket.close(code=4002, reason="missing_credentials")
        return

    ok = await _verify_proxy_token(instance_id, token)
    if not ok:
        await _safe_send(
            websocket,
            TunnelMessage(
                type=TunnelMessageType.AUTH_ERROR.value,
                payload={"reason": "invalid_credentials"},
            ),
        )
        await websocket.close(code=4003, reason="invalid_credentials")
        return

    await tunnel_hub.register(instance_id, websocket)
    await _safe_send(
        websocket,
        TunnelMessage(type=TunnelMessageType.AUTH_OK.value, payload={"instance_id": instance_id}),
    )

    ping_task = asyncio.create_task(_ping_loop(websocket, instance_id))
    try:
        while True:
            try:
                data = await websocket.receive_json()
            except WebSocketDisconnect:
                break
            if not isinstance(data, dict):
                continue
            inbound = TunnelMessage.from_dict(data)
            if inbound.type == TunnelMessageType.PONG.value:
                continue
            await ingest_host_frame(instance_id, inbound)
    finally:
        ping_task.cancel()
        try:
            await ping_task
        except asyncio.CancelledError:
            pass
        if instance_id:
            await tunnel_hub.unregister(instance_id, websocket)


async def _verify_proxy_token(instance_id: str, token: str) -> bool:
    async with get_session_factory()() as session:
        result = await session.execute(
            select(Instance).where(
                Instance.id == instance_id,
                Instance.deleted_at.is_(None),
            )
        )
        inst = result.scalar_one_or_none()
        if inst is None:
            return False
        return bool(inst.proxy_token) and inst.proxy_token == token


async def _ping_loop(websocket: WebSocket, instance_id: str) -> None:
    try:
        while True:
            await asyncio.sleep(PING_INTERVAL_S)
            ok = await tunnel_hub.send(
                instance_id,
                TunnelMessage(type=TunnelMessageType.PING.value, payload={}),
            )
            if not ok:
                break
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        logger.debug("tunnel ping loop ended instance_id=%s", instance_id, exc_info=True)


async def _safe_send(websocket: WebSocket, message: TunnelMessage) -> None:
    try:
        await websocket.send_json(message.to_dict())
    except Exception:  # noqa: BLE001
        logger.debug("tunnel send failed", exc_info=True)
