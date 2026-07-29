"""Memory API routes — append-only entity learning log.

GET  /api/v1/memory/entries  — cursor-paginated list, optional kind/key filter
POST /api/v1/memory/entries  — append a new immutable entry (201)

P6 allows any authenticated user to write any entity's memory.
P7 tightens this via instance_proxy_token.
"""

from __future__ import annotations

import base64
from datetime import datetime

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUserDep
from app.core.errors import NotFoundError
from app.core.event_types import MEMORY_ENTRY_APPENDED
from app.core.events import emit
from app.core.openapi import add_error_responses
from app.core.pagination import CursorPage, paginate_cursor
from app.models.entity import Entity
from app.models.memory import Memory
from app.schemas.memory import MemoryCreate, MemoryOut

router = APIRouter(prefix="/memory", tags=["Learning"])
add_error_responses(router)


def _encode_cursor(created_at: datetime, entry_id: str) -> str:
    raw = f"{created_at.isoformat()}::{entry_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> datetime:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    iso, _entry_id = raw.rsplit("::", 1)
    return datetime.fromisoformat(iso)


@router.get("/entries", response_model=CursorPage[MemoryOut])
async def list_memories(
    db: DB,
    current_user: CurrentUserDep,
    entity_id: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = Query(None),
    kind: str | None = Query(None),
    key: str | None = Query(None),
) -> CursorPage:
    entity = await db.get(Entity, entity_id)
    if entity is None or entity.deleted_at is not None:
        raise NotFoundError(
            "entity.not_found",
            "errors.entity.not_found",
            f"Entity '{entity_id}' not found",
        )

    if key is not None:
        stmt = (
            select(Memory)
            .where(
                Memory.entity_id == entity_id,
                Memory.key == key,
                Memory.deleted_at.is_(None),
            )
            .order_by(Memory.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        item = result.scalar_one_or_none()
        items: list[Memory] = [item] if item else []
        return CursorPage(items=items, next_cursor=None)

    stmt = select(Memory).where(
        Memory.entity_id == entity_id,
        Memory.deleted_at.is_(None),
    )
    if kind is not None:
        stmt = stmt.where(Memory.kind == kind)

    stmt = stmt.order_by(Memory.created_at.asc())

    if cursor is None:
        return await paginate_cursor(
            db, stmt, Memory.created_at, limit, _decode_cursor
        )

    page = await paginate_cursor(
        db, stmt, Memory.created_at, limit, _decode_cursor, cursor=cursor
    )
    if page.next_cursor is not None:
        last = page.items[-1]
        page.next_cursor = _encode_cursor(last.created_at, last.id)
    return page


@router.post("/entries", response_model=MemoryOut, status_code=status.HTTP_201_CREATED)
async def create_memory_entry(
    body: MemoryCreate,
    db: DB,
    current_user: CurrentUserDep,
) -> Memory:
    entity = await db.get(Entity, body.entity_id)
    if entity is None or entity.deleted_at is not None:
        raise NotFoundError(
            "entity.not_found",
            "errors.entity.not_found",
            f"Entity '{body.entity_id}' not found",
        )

    entry = Memory(**body.model_dump())
    db.add(entry)

    await emit(
        MEMORY_ENTRY_APPENDED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="memory_entry",
        resource_id=entry.id,
        payload={"entity_id": body.entity_id, "kind": body.kind},
        session=db,
    )

    await db.commit()
    await db.refresh(entry)
    return entry
