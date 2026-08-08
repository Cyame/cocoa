"""ModelCatalog offline / bundled snapshot behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.llm.model_catalog import BUNDLED_MODELS_DEV_PATH, ModelCatalog


@pytest.mark.asyncio
async def test_bundled_snapshot_used_when_network_fails() -> None:
    assert BUNDLED_MODELS_DEV_PATH.is_file(), "commit models_dev_api.json under app/resources"
    catalog = ModelCatalog(ttl_seconds=60)
    with patch.object(
        catalog,
        "_fetch_raw",
        new=AsyncMock(side_effect=RuntimeError("models.dev unreachable")),
    ):
        providers, degraded = await catalog.list_providers()
        # Background refresh fails silently; the bundled snapshot is kept.
        await catalog._refresh_task
    assert degraded is True
    assert catalog.source == "bundled"
    assert len(providers) > 10
    openai = next((p for p in providers if p.id == "openai"), None)
    assert openai is not None


@pytest.mark.asyncio
async def test_live_fetch_marks_not_degraded() -> None:
    catalog = ModelCatalog(ttl_seconds=60)
    fake = {
        "openai": {
            "id": "openai",
            "name": "OpenAI",
            "api": "https://api.openai.com/v1",
            "npm": "@ai-sdk/openai",
            "models": {"gpt-4o": {"name": "GPT-4o", "limit": {"context": 128000}}},
        }
    }
    with patch.object(catalog, "_fetch_raw", new=AsyncMock(return_value=fake)):
        await catalog.list_providers()
        # Background refresh lands the live payload.
        await catalog._refresh_task
        providers, degraded = await catalog.list_providers()
    assert degraded is False
    assert catalog.source == "live"
    assert providers[0].id == "openai"
