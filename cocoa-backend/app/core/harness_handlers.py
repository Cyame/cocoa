"""Event-dispatched handlers for the P8 harness supervisor.

Each function handles ONE ``harness.*`` event by mutating the supervisor's
in-memory registry and (for ``checkpoint``) delegating breaker evaluation
to :mod:`app.core.harness_supervisor` (which delegates to
:mod:`app.core.harness_breakers`). Handlers NEVER write to the business
DB and NEVER call ``session.commit()`` on a caller-owned session — the
P3.5 dispatcher contract.

Imports are deferred to break the circular dependency with
:mod:`app.core.harness_supervisor` (that module imports the handlers
back, so a top-level import of ``InstanceLoopMetrics`` would fail).
"""
from __future__ import annotations

from datetime import datetime, timezone

# Deferred inside handler bodies — see module docstring.


def handle_loop_started(supervisor, instance_id: str) -> None:
    """Start a new loop — stamp wall-clock and clear counters."""
    from app.core.harness_supervisor import InstanceLoopMetrics
    supervisor._registry[instance_id] = InstanceLoopMetrics(
        wall_clock_started=datetime.now(timezone.utc),
    )


async def handle_checkpoint(supervisor, instance_id: str, payload: dict) -> None:
    """Update in-memory metrics, then check the four breakers.

    Opens a short-lived SELECT-only session for the breaker config read.
    No commit is required on this session because no writes happen on
    the read path; the trip-emit session is committed inside
    :func:`app.core.harness_breakers.trip_breaker`.
    """
    from app.core.harness_supervisor import InstanceLoopMetrics
    metrics = supervisor._registry.setdefault(
        instance_id, InstanceLoopMetrics()
    )
    metrics.continuation_count += 1
    metrics.token_estimate += int(payload.get("token_estimate", 0))
    metrics.last_checkpoint_at = datetime.now(timezone.utc)

    from app.core.db import get_session_factory
    session_factory = get_session_factory()
    async with session_factory() as session:
        await supervisor._check_breakers(instance_id, session)


def handle_continuation_injected(supervisor, instance_id: str) -> None:
    """A continuation was injected — reset the idle timer."""
    metrics = supervisor._registry.get(instance_id)
    if metrics is not None:
        metrics.last_checkpoint_at = datetime.now(timezone.utc)


def handle_loop_stopped(supervisor, instance_id: str) -> None:
    """Loop stopped — drop the in-memory registry entry."""
    supervisor._registry.pop(instance_id, None)
