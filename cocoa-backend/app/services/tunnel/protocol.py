"""Eyot Tunnel WebSocket message protocol (PRD-v3.5 / P14b revival).

Frame shape aligns with Composer SSE (`chat.response.*`) and nodeskclaw Tunnel.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TunnelMessageType(str, Enum):
    # Backend -> Instance Host
    AUTH_OK = "auth.ok"
    AUTH_ERROR = "auth.error"
    CHAT_REQUEST = "chat.request"
    CONTROL = "control"
    PING = "ping"

    # Instance Host -> Backend
    AUTH = "auth"
    CHAT_RESPONSE_CHUNK = "chat.response.chunk"
    CHAT_RESPONSE_DONE = "chat.response.done"
    CHAT_RESPONSE_ERROR = "chat.response.error"
    CHAT_RESPONSE_ACTIVITY = "chat.response.activity"
    PONG = "pong"


@dataclass
class TunnelMessage:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    reply_to: str | None = None
    turn_id: str | None = None
    ts: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "payload": self.payload,
            "ts": self.ts,
        }
        if self.reply_to:
            d["reply_to"] = self.reply_to
        if self.turn_id:
            d["turn_id"] = self.turn_id
        return d

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> TunnelMessage:
        return cls(
            id=str(raw.get("id") or uuid.uuid4()),
            type=str(raw.get("type") or ""),
            payload=dict(raw.get("payload") or {}),
            reply_to=raw.get("reply_to") or raw.get("replyTo"),
            turn_id=raw.get("turn_id") or raw.get("turnId"),
            ts=int(raw.get("ts") or time.time() * 1000),
        )
