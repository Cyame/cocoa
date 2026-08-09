"""In-process Tunnel hub: instance Host ↔ Backend WebSocket registry."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from starlette.websockets import WebSocket, WebSocketState

from app.services.tunnel.protocol import TunnelMessage, TunnelMessageType

logger = logging.getLogger(__name__)

AUTH_TIMEOUT_S = 10.0
PING_INTERVAL_S = 30.0


@dataclass
class TunnelConnection:
    instance_id: str
    websocket: WebSocket
    connected_at: float = field(default_factory=time.monotonic)


class TunnelHub:
    """Singleton registry of authenticated instance Host connections."""

    def __init__(self) -> None:
        self._connections: dict[str, TunnelConnection] = {}
        self._lock = asyncio.Lock()

    def is_connected(self, instance_id: str) -> bool:
        conn = self._connections.get(instance_id)
        if conn is None:
            return False
        return conn.websocket.client_state == WebSocketState.CONNECTED

    def connected_instance_ids(self) -> list[str]:
        return [iid for iid in self._connections if self.is_connected(iid)]

    async def register(self, instance_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            old = self._connections.get(instance_id)
            if old is not None and old.websocket is not websocket:
                try:
                    await old.websocket.close(code=4003, reason="superseded")
                except Exception:  # noqa: BLE001
                    logger.debug("failed closing superseded tunnel", exc_info=True)
            self._connections[instance_id] = TunnelConnection(
                instance_id=instance_id, websocket=websocket
            )
            logger.info("tunnel registered instance_id=%s", instance_id)

    async def unregister(self, instance_id: str, websocket: WebSocket | None = None) -> None:
        async with self._lock:
            current = self._connections.get(instance_id)
            if current is None:
                return
            if websocket is not None and current.websocket is not websocket:
                return
            del self._connections[instance_id]
            logger.info("tunnel unregistered instance_id=%s", instance_id)

    async def send(self, instance_id: str, message: TunnelMessage) -> bool:
        conn = self._connections.get(instance_id)
        if conn is None or conn.websocket.client_state != WebSocketState.CONNECTED:
            return False
        try:
            await conn.websocket.send_json(message.to_dict())
            return True
        except Exception:  # noqa: BLE001
            logger.exception("tunnel send failed instance_id=%s type=%s", instance_id, message.type)
            await self.unregister(instance_id, conn.websocket)
            return False

    async def send_chat_request(
        self,
        *,
        instance_id: str,
        turn_id: str,
        text: str,
        cmd: str | None = None,
        target_entity: str | None = None,
        workspace_id: str | None = None,
    ) -> bool:
        msg = TunnelMessage(
            type=TunnelMessageType.CHAT_REQUEST.value,
            turn_id=turn_id,
            payload={
                "turn_id": turn_id,
                "text": text,
                "cmd": cmd,
                "target_entity": target_entity,
                "workspace_id": workspace_id,
                "instance_id": instance_id,
            },
        )
        return await self.send(instance_id, msg)

    async def send_control(
        self, instance_id: str, action: str, extra: dict[str, Any] | None = None
    ) -> bool:
        """Send a control frame. Generic action channel: values are neutral
        protocol primitives (interrupt / pause / resume / ...), never runtime
        names."""
        payload = {"action": action, **(extra or {})}
        msg = TunnelMessage(type=TunnelMessageType.CONTROL.value, payload=payload)
        return await self.send(instance_id, msg)


tunnel_hub = TunnelHub()


async def ingest_host_frame(instance_id: str, message: TunnelMessage) -> None:
    """Route inbound Host frames into Composer turn queues."""
    from app.core.composer_turns import ingest_tunnel_chat_frame

    msg_type = message.type
    if msg_type in (
        TunnelMessageType.CHAT_RESPONSE_CHUNK.value,
        TunnelMessageType.CHAT_RESPONSE_DONE.value,
        TunnelMessageType.CHAT_RESPONSE_ERROR.value,
    ):
        turn_id = message.turn_id or message.payload.get("turn_id")
        if not turn_id:
            logger.warning("tunnel chat frame missing turn_id type=%s", msg_type)
            return
        frame = {
            "type": msg_type,
            "turn_id": turn_id,
            "instance_id": instance_id,
            "token": message.payload.get("token"),
            "message": message.payload.get("message"),
            "target_entity": message.payload.get("target_entity"),
            "status": message.payload.get("status"),
        }
        # Drop null optional fields for cleaner SSE
        frame = {k: v for k, v in frame.items() if v is not None}
        await ingest_tunnel_chat_frame(str(turn_id), frame)
        return

    if msg_type == TunnelMessageType.PONG.value:
        return

    logger.debug("tunnel ignore inbound type=%s instance_id=%s", msg_type, instance_id)


def new_message_id() -> str:
    return str(uuid4())
