"""P14a ModelCatalog tests — verify models.dev parse, cache reuse, and builtin fallback."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.llm.model_catalog import (
    _BUILTIN_FALLBACK,
    CACHE_TTL_SECONDS,
    ModelCatalog,
    ModelInfo,
)


def _make_async_client_mock(response_payload: dict) -> MagicMock:
    """Build a MagicMock that mimics `async with httpx.AsyncClient() as client: client.get(...)`."""
    mock_client = MagicMock(name="AsyncClient")
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_response = MagicMock(name="Response")
    mock_response.raise_for_status = MagicMock(return_value=None)
    mock_response.json = MagicMock(return_value=response_payload)
    mock_client.get = AsyncMock(return_value=mock_response)
    return mock_client


def _sample_models_dev_payload() -> dict:
    """A small but representative slice of the models.dev schema."""
    return {
        "openai": {
            "name": "OpenAI",
            "models": {
                "gpt-4o": {
                    "name": "GPT-4o",
                    "limit": {"context": 128000},
                    "cost": {"input": 2.5, "output": 10.0},
                },
                "gpt-4o-mini": {
                    "name": "GPT-4o Mini",
                    "limit": {"context": 128000},
                    "cost": {"input": 0.15, "output": 0.6},
                },
            },
        },
        "anthropic": {
            "name": "Anthropic",
            "models": {
                "claude-3-5-sonnet-latest": {
                    "name": "Claude 3.5 Sonnet",
                    "limit": {"context": 200000},
                    "cost": {"input": 3.0, "output": 15.0},
                },
            },
        },
    }


@pytest.mark.asyncio
async def test_fetch_from_models_dev_mocked() -> None:
    """Given: httpx returns sample models.dev JSON.
    When: list_models() is called.
    Then: parsed ModelInfo list matches the payload structure."""
    payload = _sample_models_dev_payload()
    mock_client = _make_async_client_mock(payload)

    with patch("app.services.llm.model_catalog.httpx.AsyncClient", return_value=mock_client) as mock_cls:
        catalog = ModelCatalog()
        models = await catalog.list_models()

    mock_cls.assert_called_once_with(timeout=10.0)
    mock_client.get.assert_awaited_once()

    by_id = {m.id: m for m in models}
    # openai/gpt-4o — context + cost extracted
    gpt4o = by_id["gpt-4o"]
    assert isinstance(gpt4o, ModelInfo)
    assert gpt4o.id == "gpt-4o"
    assert gpt4o.name == "GPT-4o"
    assert gpt4o.provider == "openai"
    assert gpt4o.context_length == 128000
    assert gpt4o.pricing == {"input": 2.5, "output": 10.0}

    # anthropic/claude-3-5-sonnet-latest — also extracted
    claude = by_id["claude-3-5-sonnet-latest"]
    assert claude.provider == "anthropic"
    assert claude.context_length == 200000
    assert claude.name == "Claude 3.5 Sonnet"

    # provider filter
    openai_only = await catalog.list_models(provider="openai")
    assert {m.id for m in openai_only} == {"gpt-4o", "gpt-4o-mini"}


@pytest.mark.asyncio
async def test_cache_hit_within_600s() -> None:
    """Given: a ModelCatalog.
    When: list_models() is called twice in quick succession.
    Then: the underlying fetch is invoked exactly once (cache hit)."""
    catalog = ModelCatalog(ttl_seconds=CACHE_TTL_SECONDS)
    fetch_spy = AsyncMock(return_value=[ModelInfo(id="x", name="X", provider="test")])
    with patch.object(catalog, "_fetch_from_models_dev", fetch_spy):
        first = await catalog.list_models()
        second = await catalog.list_models()

    assert first == second == [ModelInfo(id="x", name="X", provider="test")]
    assert fetch_spy.await_count == 1, "second call must be served from cache"


@pytest.mark.asyncio
async def test_fetch_fails_fallback_to_builtin() -> None:
    """Given: httpx raises on fetch. When: list_models() is called. Then: the builtin fallback list is returned."""
    failing_client = MagicMock(name="AsyncClient")
    failing_client.__aenter__ = AsyncMock(return_value=failing_client)
    failing_client.__aexit__ = AsyncMock(return_value=None)
    failing_client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))

    with patch("app.services.llm.model_catalog.httpx.AsyncClient", return_value=failing_client):
        catalog = ModelCatalog()
        models = await catalog.list_models()

    fallback_ids = {entry["id"] for entry in _BUILTIN_FALLBACK}
    returned_ids = {m.id for m in models}
    assert returned_ids == fallback_ids
    assert all(isinstance(m, ModelInfo) for m in models)
    expected_providers = {
        "openai",
        "anthropic",
        "google",
        "deepseek",
        "alibaba",
        "meta",
        "mistral",
        "cohere",
        "xai",
        "zeroone",
        "moonshot",
    }
    assert {m.provider for m in models} == expected_providers
