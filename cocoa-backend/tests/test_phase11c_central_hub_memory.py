"""P11c Todo 9: ``handle_checkpoint_writes`` on ``harness.checkpoint`` events.

Three tests pin the wiring:

1. ``test_local_mode_writes_memory`` — given an Instance with an active
   Membership and a ``running`` loop, emitting ``HARNESS_CHECKPOINT``
   results in a fresh :class:`Memory` row whose key is
   ``checkpoint_<instance[:8]>_<iteration>``.
2. ``test_no_writes_when_loop_interrupted`` — emitting only
   ``HARNESS_INTERRUPTED`` creates no memory rows (the writer fires
   only on ``HARNESS_CHECKPOINT``).
3. ``test_handler_chains`` — registering an additional
   ``harness.checkpoint`` handler alongside the wired writer does not
   bypass the writer; both handlers run when ``HARNESS_CHECKPOINT`` is
   dispatched.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_types import (
    HARNESS_CHECKPOINT,
    HARNESS_INTERRUPTED,
)
from app.core.events import emit, register_handler
from app.core.harness_supervisor import supervisor
from app.models.central_hub import CentralHub
from app.models.loop_state import LoopStatus
from app.models.memory import Memory
from app.models.workspace import Membership

# ── fixtures copied from conftest pattern (this module is heavily filtered) ──


@pytest.fixture(autouse=True)
def _raise_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Quell rate-limit middleware during supervisor dispatch (matches P8)."""
    monkeypatch.setattr(
        "app.core.middleware.rate_limit.MAX_REQUESTS_PER_WINDOW", 100_000,
    )


@pytest_asyncio.fixture
async def wired_factory(db_url: str):  # noqa: ARG001
    """Bind session factory to the per-test DB across the supervisor chain."""
    import app.core.config as cfg
    import app.core.db as db_mod

    previous_url = cfg.settings.DATABASE_URL
    cfg.settings.DATABASE_URL = db_url
    db_mod._engine = None
    db_mod._session_factory = None
    try:
        yield
    finally:
        db_mod._engine = None
        db_mod._session_factory = None
        cfg.settings.DATABASE_URL = previous_url


async def _seed_running_instance(
    session: AsyncSession, entity_factory, workspace_factory, instance_factory,
    loop_state_factory,
    *, loop_status: str = LoopStatus.running.value,
):
    """Seed an Workspace/Entity/Instance/Membership/LoopState set up."""
    workspace = await workspace_factory()
    entity = await entity_factory()
    instance = await instance_factory(
        entity_id=entity.id, workspace_id=workspace.id,
    )
    membership = Membership(
        workspace_id=workspace.id,
        instance_id=instance.id,
        posx=0,
        posy=0,
    )
    session.add(membership)
    await loop_state_factory(instance, loop_status=loop_status)
    await session.commit()
    return workspace, entity, instance


# ── 1. CHECKPOINT writes memory + central_hub ─────────────────────────────


@pytest.mark.asyncio
async def test_local_mode_writes_memory(
    wired_factory,  # noqa: ARG001
    session: AsyncSession,
    entity_factory,
    workspace_factory,
    instance_factory,
    loop_state_factory,
) -> None:
    """A running instance's ``HARNESS_CHECKPOINT`` persists a Memory."""
    await supervisor.start()
    workspace, entity, instance = await _seed_running_instance(
        session,
        entity_factory, workspace_factory, instance_factory, loop_state_factory,
    )

    await emit(
        HARNESS_CHECKPOINT,
        actor_type="instance", actor_id=instance.id,
        resource_type="instance", resource_id=instance.id,
        payload={"token_estimate": 0, "iteration": 3},
        session=session,
    )
    await session.commit()

    result = await session.execute(
        select(Memory).where(Memory.entity_id == entity.id)
    )
    entries = list(result.scalars().all())
    assert len(entries) == 1
    entry = entries[0]
    assert entry.kind == "experience"
    assert entry.key == f"checkpoint_{instance.id[:8]}_3"
    assert "Checkpoint" in (entry.content or "")
    assert entry.source_instance_id == instance.id

    result = await session.execute(
        select(CentralHub).where(CentralHub.workspace_id == workspace.id)
    )
    central_hub = result.scalar_one()
    assert central_hub.content is not None
    assert "Checkpoint" in central_hub.content


# ── 2. Non-checkpoint events do not produce writes ───────────────────────


@pytest.mark.asyncio
async def test_no_writes_when_loop_interrupted(
    wired_factory,  # noqa: ARG001
    session: AsyncSession,
    entity_factory,
    workspace_factory,
    instance_factory,
    loop_state_factory,
) -> None:
    """Emitting only ``HARNESS_INTERRUPTED`` does NOT create a Memory."""
    await supervisor.start()
    workspace, entity, instance = await _seed_running_instance(
        session,
        entity_factory, workspace_factory, instance_factory, loop_state_factory,
        loop_status=LoopStatus.interrupted.value,
    )

    await emit(
        HARNESS_INTERRUPTED,
        actor_type="system", actor_id="system",
        resource_type="instance", resource_id=instance.id,
        payload={"action": "kill", "instance_id": instance.id},
        session=session,
    )
    await session.commit()

    memory = await session.execute(
        select(Memory).where(Memory.entity_id == entity.id)
    )
    assert list(memory.scalars().all()) == [], (
        "interrupted-only emit must not create memory entries"
    )

    central_hub = await session.execute(
        select(CentralHub).where(CentralHub.workspace_id == workspace.id)
    )
    assert central_hub.scalar_one_or_none() is None, (
        "interrupted-only emit must not lazy-create a CentralHub row"
    )

    _ = instance  # silence unused-arg on the no-member path


# ── 3. Extra handlers stay in the dispatch chain ─────────────────────────


@pytest.mark.asyncio
async def test_handler_chains(
    wired_factory,  # noqa: ARG001
    session: AsyncSession,
    entity_factory,
    workspace_factory,
    instance_factory,
    loop_state_factory,
) -> None:
    """Extra ``harness.checkpoint`` handlers fire alongside the direct-call
    writer wired into the supervisor. Asserts both pathways work without
    double-writing (the writer is invoked exactly once).
    """
    await supervisor.start()

    fired: list[str] = []

    async def extra_handler(**_kwargs: object) -> None:
        fired.append("extra")

    register_handler("harness.checkpoint", extra_handler)

    workspace, entity, instance = await _seed_running_instance(
        session,
        entity_factory, workspace_factory, instance_factory, loop_state_factory,
    )

    await emit(
        HARNESS_CHECKPOINT,
        actor_type="instance", actor_id=instance.id,
        resource_type="instance", resource_id=instance.id,
        payload={"token_estimate": 0, "iteration": 1},
        session=session,
    )
    await session.commit()

    assert fired == ["extra"], (
        f"extra handler must fire exactly once via the dispatch chain; got {fired!r}"
    )

    entries = (
        await session.execute(
            select(Memory).where(Memory.entity_id == entity.id)
        )
    ).scalars().all()
    assert len(entries) == 1, (
        f"writer must persist exactly one memory row per checkpoint; got {len(entries)}"
    )
