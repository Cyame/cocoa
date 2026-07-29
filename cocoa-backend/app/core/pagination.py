"""Cursor and offset pagination helpers for API endpoints.

Pure functions — no FastAPI dependency. Callers supply their own
:class:`sqlalchemy.ext.asyncio.AsyncSession` and pre-built
:class:`sqlalchemy.Select` queries.
"""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class CursorPage(BaseModel, Generic[T]):
    """Cursor-based pagination response.

    Fields:
        items: The list of results for this page.
        next_cursor: Opaque cursor string to fetch the next page,
            or ``None`` if this is the last page.
        total: Optional total count of matching records.
    """

    # ORM row objects (SQLAlchemy declarative models) are not Pydantic-native
    # types; allow them so CursorPage[Entity]-style usage doesn't crash.
    model_config = ConfigDict(arbitrary_types_allowed=True)

    items: list[T]
    next_cursor: str | None = None
    total: int | None = None


class OffsetPage(BaseModel, Generic[T]):
    """Offset-based pagination response.

    Fields:
        items: The list of results for this page.
        offset: 0-based offset of the first item in the page.
        limit: Maximum number of items requested.
        total: Total count of matching records.
    """

    # See CursorPage for why arbitrary types must be allowed.
    model_config = ConfigDict(arbitrary_types_allowed=True)

    items: list[T]
    offset: int
    limit: int
    total: int


# Union type for APIs that may return either pagination style.
type PaginatedResponse[T] = CursorPage[T] | OffsetPage[T]


def is_cursor_page(resp: object) -> bool:
    """Return ``True`` if *resp* is a :class:`CursorPage`."""
    return isinstance(resp, CursorPage)


def is_offset_page(resp: object) -> bool:
    """Return ``True`` if *resp* is an :class:`OffsetPage`."""
    return isinstance(resp, OffsetPage)


async def paginate_offset(
    session: AsyncSession,
    query: Select,
    offset: int,
    limit: int,
) -> OffsetPage:
    """Execute an offset/limit query and return an :class:`OffsetPage`.

    Contract:
        *query* must NOT have pre-set ``LIMIT`` / ``OFFSET`` clauses.
        This function appends them.
    """
    # Compute total count via a subquery so COUNT works on arbitrary
    # statements (JOINs, GROUP BY, etc.).
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total: int = total_result.scalar_one()

    # Fetch the requested slice.
    result = await session.execute(query.offset(offset).limit(limit))
    items: list = list(result.scalars().all())

    return OffsetPage(items=items, offset=offset, limit=limit, total=total)


async def paginate_cursor(
    session: AsyncSession,
    query: Select,
    cursor_field,
    limit: int,
    decoder,
    *,
    cursor: str | None = None,
) -> CursorPage:
    """Execute a cursor-based query and return a :class:`CursorPage`.

    Contract:
        *query* MUST already have ``.order_by(cursor_field)`` in
        **ascending** order.  This function appends a ``WHERE`` clause
        when a cursor is supplied.

    *decoder* receives the raw cursor string and must return a value
    that is comparison-compatible with *cursor_field*.

    The ``next_cursor`` is produced by calling ``str()`` on the
    *cursor_field* value of the LAST item in the returned page.  Because the
    next query filters with a strict ``>`` comparison, the extra row fetched
    beyond the page becomes the first row of the next page — no row is
    skipped at the page boundary.
    """
    if cursor is not None:
        decoded_cursor = decoder(cursor)
        query = query.where(cursor_field > decoded_cursor)

    # Fetch one extra row to detect whether another page exists.
    result = await session.execute(query.limit(limit + 1))
    all_items = list(result.scalars().all())

    has_more = len(all_items) > limit
    items: list = all_items[:limit]

    next_cursor: str | None = None
    if has_more:
        cursor_value = getattr(items[-1], cursor_field.key)
        next_cursor = str(cursor_value)

    return CursorPage(items=items, next_cursor=next_cursor)
