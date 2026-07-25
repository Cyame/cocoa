"""Messaging API schemas."""

from __future__ import annotations

from pydantic import BaseModel


class MessageSend(BaseModel):
    turn_text: str
    office_id: str


class MessageSendResult(BaseModel):
    directives: list
    general_text: str | None
    results: list
