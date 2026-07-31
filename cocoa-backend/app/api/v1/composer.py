"""Composer streaming + mention candidates + transcript history."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import DB, CurrentUserDep
from app.core.composer_turns import get_turn
from app.core.errors import NotFoundError
from app.core.openapi import add_error_responses
from app.core.passages import neighbor_membership_ids
from app.models.entity import Entity
from app.models.instance import Instance
from app.models.workspace import Membership, Workspace
from app.services.composer_transcript import (
    enrich_composer_message_items,
    list_composer_messages,
)

router = APIRouter(tags=["Composer"])
add_error_responses(router)


@router.get("/workspaces/{workspace_id}/mention-candidates")
async def list_mention_candidates(
    workspace_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> dict:
    """Passage-neighbor Lost Ones for Composer ``@`` autocomplete.

    Neighbors are duplex: an active Passage in either orientation counts.
    Typing ``@`` a non-neighbor is still parsed; delivery then routes to the
    Workspace cerebellum stub (not the Host).
    """
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None or workspace.deleted_at is not None:
        raise NotFoundError(
            "workspace.not_found",
            "errors.workspace.not_found",
            f"Workspace '{workspace_id}' not found",
        )

    sender = (
        await db.execute(
            select(Membership).where(
                Membership.workspace_id == workspace_id,
                Membership.user_id == current_user.user_id,
                Membership.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if sender is None:
        return {"items": [], "total": 0}

    to_ids = await neighbor_membership_ids(db, workspace_id, sender.id)
    if not to_ids:
        return {"items": [], "total": 0}

    mems = (
        await db.execute(
            select(Membership).where(
                Membership.id.in_(to_ids),
                Membership.instance_id.is_not(None),
                Membership.deleted_at.is_(None),
            )
        )
    ).scalars().all()

    items: list[dict] = []
    for mem in mems:
        inst = await db.get(Instance, mem.instance_id)
        if inst is None or inst.deleted_at is not None:
            continue
        entity = await db.get(Entity, inst.entity_id)
        if entity is None or entity.deleted_at is not None:
            continue
        items.append(
            {
                "entity_id": entity.id,
                "slug": entity.slug,
                "name": entity.display_name or entity.name,
                "preset_slug": entity.preset_slug,
                "instance_id": inst.id,
                "membership_id": mem.id,
                "instance_status": inst.status,
                "connected": True,
                "mentionable": inst.status == "running",
            }
        )
    return {"items": items, "total": len(items)}


@router.get("/workspaces/{workspace_id}/composer/messages")
async def list_composer_transcript(
    workspace_id: str,
    db: DB,
    current_user: CurrentUserDep,
    limit: int = Query(200, ge=1, le=500),
    instance_id: str | None = Query(
        None,
        description="When set, only messages for this Instance (Lost One scope).",
    ),
    role: str | None = Query(
        None,
        description="Filter by role: user | assistant | system",
    ),
    target_entity: str | None = Query(
        None,
        description="Filter by recipient entity slug",
    ),
    author_username: str | None = Query(
        None,
        description="Filter by speaker username (user messages)",
    ),
) -> dict:
    """Server-persisted Composer transcript (inbound + outbound).

    Composer UI omits ``instance_id`` for the global workspace view.
    Instance Host / Lost One scoped readers should pass ``instance_id``.
    Speaker/recipient filters are applied in the DB query (not client-only).
    """
    _ = current_user
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None or workspace.deleted_at is not None:
        raise NotFoundError(
            "workspace.not_found",
            "errors.workspace.not_found",
            f"Workspace '{workspace_id}' not found",
        )
    rows = await list_composer_messages(
        db,
        workspace_id,
        limit=limit,
        instance_id=instance_id,
        role=role,
        target_entity=target_entity,
        author_username=author_username,
    )
    items = await enrich_composer_message_items(db, rows)
    return {"items": items, "total": len(items)}


@router.get("/workspaces/{workspace_id}/composer/stream")
async def composer_stream(
    workspace_id: str,
    turn_id: str = Query(...),
    db: DB = None,
    current_user: CurrentUserDep = None,
):
    """SSE token stream for one Composer turn (Tunnel-shaped frames)."""
    _ = db
    _ = current_user
    state = get_turn(turn_id)
    if state is None or state.workspace_id != workspace_id:
        raise NotFoundError(
            "composer.turn_not_found",
            "errors.composer.turn_not_found",
            f"Turn '{turn_id}' not found",
        )

    async def event_gen():
        terminal_seen = False
        for frame in list(state.history):
            event_name = str(frame.get("type", "message")).replace(".", "_")
            yield f"event: {event_name}\ndata: {json.dumps(frame)}\n\n"
            if frame.get("type") in ("chat.response.done", "chat.response.error"):
                terminal_seen = True
        if terminal_seen:
            return

        yield f"event: status\ndata: {json.dumps({'type': 'composer.turn.status', 'status': state.status, 'turn_id': turn_id})}\n\n"
        while True:
            try:
                frame = await asyncio.wait_for(state.queue.get(), timeout=30.0)
            except TimeoutError:
                yield f"event: ping\ndata: {json.dumps({'type': 'ping'})}\n\n"
                if state.status in ("completed", "failed"):
                    break
                continue
            if frame is None:
                break
            event_name = str(frame.get("type", "message")).replace(".", "_")
            yield f"event: {event_name}\ndata: {json.dumps(frame)}\n\n"
            if frame.get("type") in (
                "chat.response.done",
                "chat.response.error",
            ):
                break

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
