"""P11b Todo 3: DeployRecord model tests.

Covers:

1. ``test_create_deploy_record`` — smoke test that an Instance can own a
   DeployRecord whose ``revision`` / ``action`` / ``status`` defaults are
   populated correctly when committed.

2. ``test_partial_unique_index_active_records_only`` — verifies the
   ``uq_deploy_records_instance_revision`` partial unique index:

   - two ACTIVE rows for the same ``(instance_id, revision)`` must
     collide via ``IntegrityError``;
   - after soft-deleting the first, a new row at the same ``(instance_id,
     revision)`` must commit cleanly (the partial index excludes
     ``deleted_at IS NOT NULL`` rows, mirroring the rest of Eyot).

Shared fixtures (``session``, ``instance_factory``) live in
``tests/conftest.py``.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deploy_record import (
    DeployAction,
    DeployRecord,
    DeployStatus,
)


@pytest.mark.asyncio
async def test_create_deploy_record(
    session: AsyncSession, instance_factory,
) -> None:
    """A new DeployRecord tied to an Instance gets the expected defaults."""
    instance = await instance_factory()

    record = DeployRecord(instance_id=instance.id)
    session.add(record)
    await session.commit()
    await session.refresh(record)

    assert record.id is not None
    assert record.instance_id == instance.id
    assert record.revision == 1
    assert record.action == DeployAction.deploy.value
    assert record.status == DeployStatus.pending.value
    assert record.image_version is None
    assert record.config_snapshot is None
    assert record.message is None
    assert record.triggered_by is None
    assert record.started_at is None
    assert record.finished_at is None
    assert record.deleted_at is None


@pytest.mark.asyncio
async def test_partial_unique_index_active_records_only(
    session: AsyncSession, instance_factory,
) -> None:
    """Two active records at the same ``(instance_id, revision)`` must
    collide; once the first is soft-deleted, the same slot can be
    reused by a fresh active record.
    """
    instance = await instance_factory()
    # Capture instance.id eagerly — async session may expire ORM attributes
    # after an IntegrityError + rollback, and re-accessing ``instance.id``
    # would trigger a lazy load outside the greenlet context.
    instance_id = instance.id

    first = DeployRecord(instance_id=instance_id, revision=1)
    session.add(first)
    await session.commit()

    # Collision: another active row at the same (instance_id, revision=1).
    duplicate = DeployRecord(instance_id=instance_id, revision=1)
    session.add(duplicate)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()

    # Soft-delete the first; partial index now allows the slot to be reused.
    first.soft_delete()
    await session.commit()

    revived = DeployRecord(instance_id=instance_id, revision=1)
    session.add(revived)
    await session.commit()
    await session.refresh(revived)

    assert revived.id is not None
    assert revived.deleted_at is None
    assert revived.instance_id == instance_id
    assert revived.revision == 1
