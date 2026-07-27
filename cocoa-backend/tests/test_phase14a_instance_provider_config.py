"""P14a InstanceProviderConfig model tests — Todo 5 of Wave 2.

Two regressions:

1. ``test_create_provider_config`` — verify ``InstanceProviderConfig`` can be
   created and round-trips through the DB (id auto-generated, fields persisted).
2. ``test_partial_unique_index_active_records_only`` — verify the partial
   unique index allows re-creating a config after the prior one is soft
   deleted (the soft-delete + partial-unique-index invariant from AGENTS.md
   "软删除规则").

Both tests rely on the per-test cloned DB (conftest isolates via TEMPLATE).
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instance_provider_config import InstanceProviderConfig


@pytest.mark.asyncio
async def test_create_provider_config(
    session: AsyncSession,
    instance_factory,
) -> None:
    """A fresh ``InstanceProviderConfig`` persists with auto-id and all fields."""
    instance = await instance_factory()

    config = InstanceProviderConfig(
        instance_id=instance.id,
        provider_type="openai-compatible",
        api_key_ref="OPENAI_API_KEY",
        default_model="gpt-4o-mini",
        selected_models={"chat": "gpt-4o-mini", "embed": "text-embedding-3-small"},
    )
    session.add(config)
    await session.commit()

    assert config.id is not None
    assert config.provider_type == "openai-compatible"
    assert config.api_key_ref == "OPENAI_API_KEY"
    assert config.default_model == "gpt-4o-mini"
    assert config.selected_models == {
        "chat": "gpt-4o-mini",
        "embed": "text-embedding-3-small",
    }
    assert config.base_url is None
    assert config.deleted_at is None


@pytest.mark.asyncio
async def test_partial_unique_index_active_records_only(
    session: AsyncSession,
    instance_factory,
) -> None:
    """Partial unique index allows re-creation after soft delete.

    Live (deleted_at IS NULL) records enforce one row per
    (instance_id, provider_type); soft-deleted rows don't participate,
    so a fresh config with the same key is permitted after soft delete.
    """
    instance = await instance_factory()
    # Capture instance.id eagerly — async session may expire ORM attributes
    # after an IntegrityError + rollback, and re-accessing ``instance.id``
    # would trigger a lazy load outside the greenlet context.
    instance_id = instance.id

    config1 = InstanceProviderConfig(
        instance_id=instance_id,
        provider_type="anthropic",
        api_key_ref="ANTHROPIC_API_KEY",
        default_model="claude-3-5-haiku-latest",
    )
    session.add(config1)
    await session.commit()

    # Duplicate (instance_id, provider_type) on an active row must fail.
    dup = InstanceProviderConfig(
        instance_id=instance_id,
        provider_type="anthropic",
        api_key_ref="ANTHROPIC_API_KEY",
        default_model="claude-3-5-haiku-latest",
    )
    session.add(dup)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()

    # Soft delete the first config; partial unique index no longer covers it.
    config1.soft_delete()
    await session.commit()

    # Now a fresh config with the same (instance_id, provider_type) works.
    config3 = InstanceProviderConfig(
        instance_id=instance_id,
        provider_type="anthropic",
        api_key_ref="ANTHROPIC_API_KEY",
        default_model="claude-3-5-haiku-latest",
    )
    session.add(config3)
    await session.commit()
    assert config3.id is not None
