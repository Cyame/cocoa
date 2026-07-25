"""In-process event dispatcher with best-effort handler dispatch.

Contracts
---------
1. **Handler registration point = Redis Streams bridge point.**
   P6/P8 will replace or augment in-process handlers by registering a forwarding
   handler that publishes to Redis Streams.  The ``register_handler`` API is the
   single seam where that bridge attaches — no other code needs to change.

2. **Commit proximity contract.**
   Handlers are invoked *before* the calling transaction commits.  ``emit()``
   MUST only be called in a context that is about to commit.  Handlers MUST
   tolerate rollback (phantom events) — or use ``after_commit`` session events
   inside the handler to defer work until after the commit succeeds.

   ``emit()`` calls ``session.flush()`` so the Event row is visible to handlers
   within the same transaction, but it never calls ``session.commit()`` — the
   caller owns the transaction boundary.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Callable
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event

# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

_handlers: list[tuple[str, Callable[..., Any]]] = []


def register_handler(pattern: str, handler: Callable[..., Any]) -> None:
    """Register a best-effort event handler.

    ``pattern`` is matched against ``event.type`` with
    :func:`fnmatch.fnmatchcase`.  Shell-style wildcards are supported
    (``*``, ``?``, ``[seq]``).  ``fnmatchcase`` is used over ``fnmatch``
    to keep behaviour identical on Windows and Unix.

    The handler is called with keyword arguments matching the full set of
    ``emit()`` parameters so that handlers can be written with a signature
    like ``async def my_handler(event, **kwargs)`` or
    ``async def my_handler(event_type, actor_type, ..., payload, **kwargs)``.
    """
    _handlers.append((pattern, handler))


# ---------------------------------------------------------------------------
# emit
# ---------------------------------------------------------------------------


async def emit(
    event_type: str,
    *,
    actor_type: str,
    actor_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    payload: dict[str, Any] | None = None,
    request_id: str | None = None,
    session: AsyncSession,
) -> Event:
    """Persist an audit event and dispatch to matching best-effort handlers.

    Parameters
    ----------
    event_type:
        Dot-separated event type string, e.g. ``"system.startup"``.
    actor_type:
        Kind of actor that triggered the event (``"system"``, ``"user"``, …).
    actor_id:
        Optional UUID of the actor.
    resource_type:
        Optional kind of affected resource.
    resource_id:
        Optional UUID of the affected resource.
    payload:
        Optional free-form JSON-serialisable payload.
    request_id:
        Optional correlation id from the inbound HTTP request.
    session:
        An active :class:`~sqlalchemy.ext.asyncio.AsyncSession` owned by the
        caller.  ``emit()`` calls ``session.flush()`` but never commits.

    Returns
    -------
    The persisted :class:`~app.models.event.Event` row.

    Raises
    ------
    Exception
        Only if writing the event row to the database fails (DB unreachable).
        Handler exceptions are **never** propagated — they are logged and
        swallowed (best-effort contract).
    """
    event = Event(
        type=event_type,
        actor_type=actor_type,
        actor_id=actor_id,
        resource_type=resource_type,
        resource_id=resource_id,
        payload=payload if payload is not None else {},
        request_id=request_id,
    )
    session.add(event)
    await session.flush()

    # Best-effort dispatch: every handler runs in its own try/except so
    # that one failing handler never blocks or crashes the others.
    for pattern, handler in _handlers:
        if not fnmatch.fnmatchcase(event_type, pattern):
            continue
        try:
            await handler(
                event=event,
                event_type=event_type,
                actor_type=actor_type,
                actor_id=actor_id,
                resource_type=resource_type,
                resource_id=resource_id,
                payload=payload,
                request_id=request_id,
            )
        except Exception:
            logger.opt(exception=True).error(
                "Event handler failed",
                event_type=event_type,
                handler=getattr(handler, "__name__", repr(handler)),
            )

    return event
