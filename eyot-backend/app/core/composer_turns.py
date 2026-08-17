"""Composer turn scheduling + in-memory stream queues (PRD-v3.4.1 / v3.5 Tunnel).

Aligns with Tunnel final shape: chat.response.chunk / done / error + turn status.
When Instance Host is connected via Tunnel, chat runs on pi; otherwise stub/LLM fallback.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_types import (
    CHAT_RESPONSE_ACTIVITY,
    CHAT_RESPONSE_CHUNK,
    CHAT_RESPONSE_DONE,
    CHAT_RESPONSE_ERROR,
    HARNESS_CONTROL_SENT,
)
from app.core.events import emit
from app.services.llm.llm_client import LLMClient, LLMError, TokenChunk

logger = logging.getLogger(__name__)

TurnStatus = str  # responding | completed | failed


@dataclass
class ComposerTurnState:
    turn_id: str
    instance_id: str
    workspace_id: str
    target_entity: str
    status: TurnStatus = "responding"
    text: str = ""  # user prompt
    reply_text: str = ""  # accumulated assistant reply
    queue: asyncio.Queue[dict[str, Any] | None] = field(default_factory=asyncio.Queue)
    # Late SSE subscribers replay these (stub/LLM may finish before client connects).
    history: list[dict[str, Any]] = field(default_factory=list)
    via_tunnel: bool = False
    user_message_id: str | None = None
    assistant_message_id: str | None = None
    from_user_id: str | None = None


_TURNS: dict[str, ComposerTurnState] = {}


def get_turn(turn_id: str) -> ComposerTurnState | None:
    return _TURNS.get(turn_id)


def list_workspace_turns(workspace_id: str) -> list[ComposerTurnState]:
    return [t for t in _TURNS.values() if t.workspace_id == workspace_id]


def instance_has_active_turn(instance_id: str) -> bool:
    """True when Composer has an in-flight turn for this Instance (Host chatting)."""
    return any(
        t.instance_id == instance_id and t.status == "responding" for t in _TURNS.values()
    )


async def _emit_frame(state: ComposerTurnState, frame: dict[str, Any]) -> None:
    state.history.append(frame)
    await state.queue.put(frame)


async def ingest_tunnel_chat_frame(turn_id: str, frame: dict[str, Any]) -> None:
    """Apply an inbound Tunnel chat.response.* frame to a Composer turn."""
    state = _TURNS.get(turn_id)
    if state is None:
        logger.warning("tunnel frame for unknown turn_id=%s type=%s", turn_id, frame.get("type"))
        return

    frame = {
        **frame,
        "turn_id": turn_id,
        "instance_id": state.instance_id,
        "target_entity": frame.get("target_entity") or state.target_entity,
    }
    msg_type = frame.get("type")
    if msg_type == CHAT_RESPONSE_CHUNK:
        if "status" not in frame:
            frame["status"] = "responding"
        token = frame.get("token")
        if isinstance(token, str) and token:
            state.reply_text += token
        await _emit_frame(state, frame)
        await _persist_chat_event(CHAT_RESPONSE_CHUNK, state, frame)
        return

    if msg_type == CHAT_RESPONSE_DONE:
        state.status = "completed"
        frame.setdefault("status", "completed")
        done_text = frame.get("text")
        # Done payload is authoritative when present; otherwise keep chunks.
        if isinstance(done_text, str) and done_text.strip():
            state.reply_text = done_text
        if "text" not in frame or not frame.get("text"):
            frame["text"] = state.reply_text
        await _emit_frame(state, frame)
        await _persist_chat_event(CHAT_RESPONSE_DONE, state, frame)
        await _finalize_assistant_message(state, status="completed")
        await state.queue.put(None)
        return

    if msg_type == CHAT_RESPONSE_ERROR:
        state.status = "failed"
        frame.setdefault("status", "failed")
        await _emit_frame(state, frame)
        await _persist_chat_event(CHAT_RESPONSE_ERROR, state, frame)
        await _finalize_assistant_message(
            state, status="failed", content=str(frame.get("message") or state.reply_text)
        )
        await state.queue.put(None)
        return

    if msg_type == CHAT_RESPONSE_ACTIVITY:
        # 流式活动回显（thinking / tool_use）：透传 host payload，不改变
        # turn 状态与回复文本，也不终结 turn。
        await _emit_frame(state, frame)
        await _persist_chat_event(CHAT_RESPONSE_ACTIVITY, state, frame)
        return

    logger.debug("ignore non-chat tunnel frame type=%s", msg_type)


async def schedule_user_turn(
    *,
    session: AsyncSession,
    workspace_id: str,
    instance_id: str,
    target_entity: str,
    text: str,
    cmd: str | None,
    from_membership_id: str,
) -> str:
    """Enqueue a user turn: Tunnel chat.request when Host online, else stub stream."""
    from app.models.workspace import Membership
    from app.services.composer_transcript import append_composer_message

    turn_id = str(uuid4())
    sender = await session.get(Membership, from_membership_id)
    from_user_id = sender.user_id if sender is not None else None

    user_row = await append_composer_message(
        session,
        workspace_id=workspace_id,
        role="user",
        content=text,
        target_entity=target_entity,
        instance_id=instance_id,
        turn_id=turn_id,
        status="completed",
        author_user_id=from_user_id,
    )
    assistant_row = await append_composer_message(
        session,
        workspace_id=workspace_id,
        role="assistant",
        content="",
        target_entity=target_entity,
        instance_id=instance_id,
        turn_id=turn_id,
        status="responding",
    )

    state = ComposerTurnState(
        turn_id=turn_id,
        instance_id=instance_id,
        workspace_id=workspace_id,
        target_entity=target_entity,
        status="responding",
        text=text,
        user_message_id=user_row.id if user_row else None,
        assistant_message_id=assistant_row.id if assistant_row else None,
        from_user_id=from_user_id,
    )
    _TURNS[turn_id] = state

    await emit(
        HARNESS_CONTROL_SENT,
        actor_type="membership",
        actor_id=from_membership_id,
        resource_type="instance",
        resource_id=instance_id,
        payload={
            "action": "user_turn",
            "instance_id": instance_id,
            "turn_id": turn_id,
            "text": text,
            "cmd": cmd,
            "target_entity": target_entity,
            "workspace_id": workspace_id,
        },
        session=session,
    )

    from app.services.tunnel.tunnel_hub import tunnel_hub

    if tunnel_hub.is_connected(instance_id):
        state.via_tunnel = True
        sent = await tunnel_hub.send_chat_request(
            instance_id=instance_id,
            turn_id=turn_id,
            text=text,
            cmd=cmd,
            target_entity=target_entity,
            workspace_id=workspace_id,
        )
        if sent:
            logger.info(
                "composer turn via tunnel turn_id=%s instance_id=%s",
                turn_id,
                instance_id,
            )
            return turn_id
        logger.warning(
            "tunnel.offline_fallback after send fail turn_id=%s instance_id=%s",
            turn_id,
            instance_id,
        )
        state.via_tunnel = False
    else:
        logger.info(
            "tunnel.offline_fallback turn_id=%s instance_id=%s",
            turn_id,
            instance_id,
        )

    asyncio.create_task(
        _run_stream_turn(state),
        name=f"composer-turn-{turn_id[:8]}",
    )
    return turn_id


async def _run_stream_turn(state: ComposerTurnState) -> None:
    """Backend-side LLM stream (HTTP Transport path); emits Tunnel-shaped events."""
    user_content = state.text.strip() or "(empty)"
    try:
        async for chunk in _iter_tokens(user_content):
            if chunk.token:
                state.reply_text += chunk.token
                frame = {
                    "type": CHAT_RESPONSE_CHUNK,
                    "turn_id": state.turn_id,
                    "instance_id": state.instance_id,
                    "target_entity": state.target_entity,
                    "token": chunk.token,
                    "status": "responding",
                }
                await _emit_frame(state, frame)
                await _persist_chat_event(CHAT_RESPONSE_CHUNK, state, frame)
            if chunk.finish_reason:
                state.status = "completed"
                done = {
                    "type": CHAT_RESPONSE_DONE,
                    "turn_id": state.turn_id,
                    "instance_id": state.instance_id,
                    "target_entity": state.target_entity,
                    "finish_reason": chunk.finish_reason,
                    "status": "completed",
                    "text": state.reply_text,
                }
                await _emit_frame(state, done)
                await _persist_chat_event(CHAT_RESPONSE_DONE, state, done)
                await _finalize_assistant_message(state, status="completed")
                break
        else:
            state.status = "completed"
            done = {
                "type": CHAT_RESPONSE_DONE,
                "turn_id": state.turn_id,
                "instance_id": state.instance_id,
                "target_entity": state.target_entity,
                "finish_reason": "stop",
                "status": "completed",
                "text": state.reply_text,
            }
            await _emit_frame(state, done)
            await _persist_chat_event(CHAT_RESPONSE_DONE, state, done)
            await _finalize_assistant_message(state, status="completed")
    except LLMError as exc:
        state.status = "failed"
        err = {
            "type": CHAT_RESPONSE_ERROR,
            "turn_id": state.turn_id,
            "instance_id": state.instance_id,
            "target_entity": state.target_entity,
            "message": str(exc),
            "status": "failed",
        }
        await _emit_frame(state, err)
        await _persist_chat_event(CHAT_RESPONSE_ERROR, state, err)
        await _finalize_assistant_message(state, status="failed", content=str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("composer turn failed turn_id=%s", state.turn_id)
        state.status = "failed"
        err = {
            "type": CHAT_RESPONSE_ERROR,
            "turn_id": state.turn_id,
            "instance_id": state.instance_id,
            "target_entity": state.target_entity,
            "message": str(exc),
            "status": "failed",
        }
        await _emit_frame(state, err)
        await _persist_chat_event(CHAT_RESPONSE_ERROR, state, err)
        await _finalize_assistant_message(state, status="failed", content=str(exc))
    finally:
        await state.queue.put(None)


async def _finalize_assistant_message(
    state: ComposerTurnState,
    *,
    status: str,
    content: str | None = None,
) -> None:
    """Persist assistant bubble content/status after a turn finishes."""
    from app.core.db import get_session_factory
    from app.services.composer_transcript import update_composer_message_by_turn

    body = content if content is not None else state.reply_text
    if not (body or "").strip() and (state.reply_text or "").strip():
        body = state.reply_text
    try:
        async with get_session_factory()() as session:
            await update_composer_message_by_turn(
                session,
                turn_id=state.turn_id,
                role="assistant",
                content=body,
                status=status,
            )
            await session.commit()
    except Exception:  # noqa: BLE001
        logger.exception(
            "finalize assistant message failed turn_id=%s", state.turn_id
        )


async def _iter_tokens(user_content: str):
    """Yield TokenChunks from real LLM or deterministic stub (no API key)."""
    import os

    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key or api_key == "stub":
        reply = f"[stub] {user_content}"
        # Word-ish chunks so Composer can demonstrate streaming without a key.
        parts = reply.split(" ")
        for i, part in enumerate(parts):
            token = part if i == 0 else f" {part}"
            yield TokenChunk(token=token, finish_reason=None)
            await asyncio.sleep(0.03)
        yield TokenChunk(token="", finish_reason="stop")
        return

    client = LLMClient(
        provider_type="openai-compatible",
        api_key=api_key,
        base_url=os.environ.get("OPENAI_BASE_URL"),
        default_model=os.environ.get("EYOT_DEFAULT_MODEL", "gpt-4o-mini"),
    )
    messages = [{"role": "user", "content": user_content}]
    async for chunk in client.stream(messages):
        yield chunk


async def _persist_chat_event(
    event_type: str, state: ComposerTurnState, payload: dict[str, Any]
) -> None:
    from app.core.db import get_session_factory

    try:
        async with get_session_factory()() as session:
            await emit(
                event_type,
                actor_type="instance",
                actor_id=state.instance_id,
                resource_type="instance",
                resource_id=state.instance_id,
                payload=payload,
                session=session,
            )
            await session.commit()
    except Exception:  # noqa: BLE001
        logger.exception("persist chat event failed type=%s", event_type)
