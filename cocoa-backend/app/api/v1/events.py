"""Event audit query endpoint.

GET /api/v1/events  — cursor-paginated audit log with 6 filters.

The events table is append-only (P3.5 contract). This endpoint is
read-only and serves P9 debug panels (Topology viz corridor-animation
detection, Instance detail event panel, Debug page raw event stream).

No POST / PATCH / DELETE — the audit log is write-once. No ``emit()`` is
performed by this endpoint.

Pagination
----------
Display order is newest-first: ``(Event.created_at.desc(), Event.id.desc())``.

The cursor encodes the compound key ``(created_at, id)`` so that two
events sharing the same ``created_at`` (possible because UUIDs are
random, not time-sortable) do not collide at the page boundary. Filter
uses the SQL row-value ``(created_at, id) < (decoded)`` form which
PostgreSQL evaluates as the lexicographic tuple comparison.

The compound key is what makes the plan's stated ``paginate_cursor``
helper a poor fit — that helper assumes a single ``cursor_field`` and
``>`` filter, which would either miss same-timestamp rows or break the
newest-first sort. The pattern here mirrors :mod:`app.api.v1.memory`'s
base64 cursor but inverts the comparison direction for DESC.
"""

from __future__ import annotations

import base64
from datetime import datetime

from fastapi import APIRouter, Query
from sqlalchemy import select, tuple_

from app.api.deps import DB, CurrentUserDep
from app.core.openapi import add_error_responses
from app.core.pagination import CursorPage
from app.models.event import Event
from app.schemas.event import EventOut

router = APIRouter(prefix="/events", tags=["Events"])
add_error_responses(router)


def _encode_cursor(created_at: datetime, event_id: str) -> str:
    """Pack ``(created_at, id)`` into an opaque base64 cursor string."""
    raw = f"{created_at.isoformat()}::{event_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    """Reverse :func:`_encode_cursor`; raises ``ValueError`` on bad input."""
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    iso, event_id = raw.rsplit("::", 1)
    return datetime.fromisoformat(iso), event_id


@router.get("", response_model=CursorPage[EventOut])
async def list_events(
    db: DB,
    current_user: CurrentUserDep,
    type_prefix: str | None = Query(None, description="Filter by event.type LIKE '<prefix>%'"),
    resource_type: str | None = Query(None),
    resource_id: str | None = Query(None),
    request_id: str | None = Query(None),
    since: datetime | None = Query(None, description="Inclusive lower bound on created_at"),
    until: datetime | None = Query(None, description="Inclusive upper bound on created_at"),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = Query(None),
) -> CursorPage[EventOut]:
    """List audit events newest-first with cursor pagination + 6 filters.

    Filters are all optional and combined with AND. ``type_prefix``
    matches via SQL ``LIKE 'prefix%'``; the other five are equality
    except ``since``/``until`` which are inclusive range bounds on
    ``created_at``.

    Events have no soft-delete — the audit log is append-only — so we
    do NOT add a ``deleted_at IS NULL`` filter.
    """
    stmt = select(Event)

    if type_prefix is not None:
        stmt = stmt.where(Event.type.like(f"{type_prefix}%"))
    if resource_type is not None:
        stmt = stmt.where(Event.resource_type == resource_type)
    if resource_id is not None:
        stmt = stmt.where(Event.resource_id == resource_id)
    if request_id is not None:
        stmt = stmt.where(Event.request_id == request_id)
    if since is not None:
        stmt = stmt.where(Event.created_at >= since)
    if until is not None:
        stmt = stmt.where(Event.created_at <= until)

    if cursor is not None:
        decoded_ts, decoded_id = _decode_cursor(cursor)
        # DESC: next page is strictly older than the last item of the
        # previous page. Lexicographic (created_at, id) < (decoded) keeps
        # the (created_at DESC, id DESC) ordering stable.
        stmt = stmt.where(
            tuple_(Event.created_at, Event.id) < tuple_(decoded_ts, decoded_id)
        )

    stmt = stmt.order_by(Event.created_at.desc(), Event.id.desc())

    # Fetch one extra row to detect another page without a second query.
    result = await db.execute(stmt.limit(limit + 1))
    all_items = list(result.scalars().all())
    has_more = len(all_items) > limit
    items: list[Event] = all_items[:limit]

    next_cursor: str | None = None
    if has_more and items:
        last = items[-1]
        next_cursor = _encode_cursor(last.created_at, last.id)

    return CursorPage(items=items, next_cursor=next_cursor)
