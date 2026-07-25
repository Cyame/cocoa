"""Memory API routes — append-only employee learning log.

GET  /api/v1/memory/entries  — cursor-paginated list, optional kind/key filter
POST /api/v1/memory/entries  — append a new immutable entry (201)

P6 allows any authenticated user to write any employee's memory.
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
from app.models.employee import Employee
from app.models.memory import MemoryEntry
from app.schemas.memory import MemoryEntryCreate, MemoryEntryOut

router = APIRouter(prefix="/memory", tags=["Learning"])
add_error_responses(router)


def _encode_cursor(created_at: datetime, entry_id: str) -> str:
    raw = f"{created_at.isoformat()}::{entry_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> datetime:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    iso, _entry_id = raw.rsplit("::", 1)
    return datetime.fromisoformat(iso)


@router.get("/entries", response_model=CursorPage[MemoryEntryOut])
async def list_memory_entries(
    db: DB,
    current_user: CurrentUserDep,
    employee_id: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = Query(None),
    kind: str | None = Query(None),
    key: str | None = Query(None),
) -> CursorPage:
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.deleted_at is not None:
        raise NotFoundError(
            "employee.not_found",
            "errors.employee.not_found",
            f"Employee '{employee_id}' not found",
        )

    if key is not None:
        stmt = (
            select(MemoryEntry)
            .where(
                MemoryEntry.employee_id == employee_id,
                MemoryEntry.key == key,
                MemoryEntry.deleted_at.is_(None),
            )
            .order_by(MemoryEntry.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        item = result.scalar_one_or_none()
        items: list[MemoryEntry] = [item] if item else []
        return CursorPage(items=items, next_cursor=None)

    stmt = select(MemoryEntry).where(
        MemoryEntry.employee_id == employee_id,
        MemoryEntry.deleted_at.is_(None),
    )
    if kind is not None:
        stmt = stmt.where(MemoryEntry.kind == kind)

    stmt = stmt.order_by(MemoryEntry.created_at.asc())

    if cursor is None:
        return await paginate_cursor(
            db, stmt, MemoryEntry.created_at, limit, _decode_cursor
        )

    page = await paginate_cursor(
        db, stmt, MemoryEntry.created_at, limit, _decode_cursor, cursor=cursor
    )
    if page.next_cursor is not None:
        last = page.items[-1]
        page.next_cursor = _encode_cursor(last.created_at, last.id)
    return page


@router.post("/entries", response_model=MemoryEntryOut, status_code=status.HTTP_201_CREATED)
async def create_memory_entry(
    body: MemoryEntryCreate,
    db: DB,
    current_user: CurrentUserDep,
) -> MemoryEntry:
    employee = await db.get(Employee, body.employee_id)
    if employee is None or employee.deleted_at is not None:
        raise NotFoundError(
            "employee.not_found",
            "errors.employee.not_found",
            f"Employee '{body.employee_id}' not found",
        )

    entry = MemoryEntry(**body.model_dump())
    db.add(entry)

    await emit(
        MEMORY_ENTRY_APPENDED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="memory_entry",
        resource_id=entry.id,
        payload={"employee_id": body.employee_id, "kind": body.kind},
        session=db,
    )

    await db.commit()
    await db.refresh(entry)
    return entry
