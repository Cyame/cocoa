"""P14a ModelCatalog tests — verify models.dev parse, cache reuse, and builtin fallback."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.llm.model_catalog import (
    _BUILTIN_FALLBACK,
    CACHE_TTL_SECONDS,
    ModelCatalog,
    ModelInfo,
    infer_image_gen,
    infer_model_type,
    infer_video,
    infer_vision,
    infer_web_search,
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
    """First call serves the bundled snapshot without blocking; a background
    refresh then swaps in the live models.dev payload."""
    payload = _sample_models_dev_payload()
    mock_client = _make_async_client_mock(payload)

    with patch("app.services.llm.model_catalog.httpx.AsyncClient", return_value=mock_client) as mock_cls:
        catalog = ModelCatalog()
        snapshot = await catalog.list_models()
        # Immediate snapshot: no network wait on the first call.
        assert catalog.source == "bundled"
        assert catalog.degraded is True
        assert len(snapshot) > 0
        # Background refresh completes and updates the cache.
        assert catalog._refresh_task is not None
        await catalog._refresh_task
        models = await catalog.list_models()

    mock_cls.assert_called_once_with(timeout=10.0)
    mock_client.get.assert_awaited_once()
    assert catalog.source == "live"
    assert catalog.degraded is False

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
    When: list_models() is called repeatedly.
    Then: the background fetch runs exactly once; later calls are served from cache."""
    catalog = ModelCatalog(ttl_seconds=CACHE_TTL_SECONDS)
    fetch_spy = AsyncMock(return_value=_sample_models_dev_payload())
    with patch.object(catalog, "_fetch_raw", fetch_spy):
        await catalog.list_models()
        await catalog._refresh_task
        first = await catalog.list_models()
        second = await catalog.list_models()

    assert first == second
    assert {m.id for m in first} == {"gpt-4o", "gpt-4o-mini", "claude-3-5-sonnet-latest"}
    assert fetch_spy.await_count == 1, "fetch happens once; later calls are served from cache"


@pytest.mark.asyncio
async def test_fetch_fails_fallback_to_builtin() -> None:
    """Given: httpx raises on fetch. When: list_models() is called. Then: the builtin fallback list is returned."""
    failing_client = MagicMock(name="AsyncClient")
    failing_client.__aenter__ = AsyncMock(return_value=failing_client)
    failing_client.__aexit__ = AsyncMock(return_value=None)
    failing_client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))

    with patch(
        "app.services.llm.model_catalog.httpx.AsyncClient", return_value=failing_client
    ), patch.object(ModelCatalog, "_load_bundled_raw", return_value=None):
        catalog = ModelCatalog()
        models = await catalog.list_models()
        # Background refresh fails silently; the builtin snapshot is kept.
        await catalog._refresh_task

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


def _rich_models_dev_payload() -> dict:
    """models.dev slice with the full capability surface (v5.2.1 G16)."""
    return {
        "openai": {
            "name": "OpenAI",
            "models": {
                "gpt-4o": {
                    "name": "GPT-4o",
                    "description": "Omnivorous flagship",
                    "limit": {"context": 128000, "output": 16384},
                    "cost": {"input": 2.5, "output": 10.0},
                    "reasoning": False,
                    "tool_call": True,
                    "attachment": True,
                    "modalities": {"input": ["text", "image"], "output": ["text"]},
                },
                "text-embedding-3-small": {
                    "name": "Embedding Small",
                    "limit": {"context": 8191},
                    "cost": {"input": 0.02},
                },
            },
        },
        "anthropic": {
            "name": "Anthropic",
            "models": {
                "claude-3-5-sonnet-latest": {
                    "name": "Claude 3.5 Sonnet",
                    "limit": {"context": 200000, "output": 8192},
                    "reasoning": True,
                    "tool_call": True,
                    "attachment": False,
                    "modalities": {"input": ["text", "image"], "output": ["text"]},
                },
            },
        },
        "openai-tts": {
            "name": "OpenAI TTS",
            "models": {
                "tts-1": {
                    "name": "TTS 1",
                    "modalities": {"input": ["text"], "output": ["audio"]},
                },
            },
        },
    }


@pytest.mark.asyncio
async def test_parse_extracts_capability_fields() -> None:
    """Given: models.dev raw with capability fields.
    When: _parse_models runs.
    Then: every capability field lands on ModelInfo (None-safe for sparse entries)."""
    catalog = ModelCatalog(ttl_seconds=60)
    models = catalog._parse_models(_rich_models_dev_payload())
    by_id = {m.id: m for m in models}

    gpt4o = by_id["gpt-4o"]
    assert gpt4o.description == "Omnivorous flagship"
    assert gpt4o.reasoning is False
    assert gpt4o.tool_call is True
    assert gpt4o.attachment is True
    assert gpt4o.modalities == {"input": ["text", "image"], "output": ["text"]}
    assert gpt4o.limit_output == 16384
    assert gpt4o.cost == {"input": 2.5, "output": 10.0}
    assert gpt4o.pricing == gpt4o.cost

    claude = by_id["claude-3-5-sonnet-latest"]
    assert claude.reasoning is True
    assert claude.limit_output == 8192

    embedding = by_id["text-embedding-3-small"]
    assert embedding.limit_output is None
    assert embedding.reasoning is None
    assert embedding.tool_call is None
    assert embedding.attachment is None
    assert embedding.modalities is None
    assert embedding.cost == {"input": 0.02}


def test_infer_vision_from_modalities_and_attachment() -> None:
    assert infer_vision({"input": ["text", "image"], "output": ["text"]}) is True
    assert infer_vision({"input": ["text"], "output": ["text"]}) is False
    assert infer_vision({"input": ["text"], "output": ["text"]}, attachment=True) is True
    assert infer_vision(None, attachment=True) is True
    assert infer_vision(None) is None
    assert infer_vision({"input": ["video"], "output": ["text"]}) is False


def test_infer_image_gen_from_output_modalities() -> None:
    assert infer_image_gen({"input": ["text"], "output": ["image"]}) is True
    assert infer_image_gen({"input": ["text"], "output": ["text"]}) is False
    assert infer_image_gen(None) is None


def test_infer_video_from_input_modalities() -> None:
    assert infer_video({"input": ["text", "video"], "output": ["text"]}) is True
    assert infer_video({"input": ["text"], "output": ["text"]}) is False
    assert infer_video(None) is None


def test_infer_web_search_always_undetermined() -> None:
    assert infer_web_search({"input": ["text"], "output": ["text"]}) is None
    assert infer_web_search(None) is None


def test_infer_model_type_suggestions() -> None:
    assert infer_model_type({"input": ["text"], "output": ["text"]}) == "chat"
    assert infer_model_type({"input": ["text"], "output": ["audio"]}) == "tts"
    assert infer_model_type({"input": ["audio"], "output": ["text"]}) == "asr"
    assert infer_model_type({"input": ["text"], "output": ["image"]}) == "image"
    assert infer_model_type({"input": ["text"], "output": ["video"]}) == "video"
    assert infer_model_type({"input": ["audio"], "output": ["audio"]}) == "realtime"
    assert infer_model_type({"input": ["image"], "output": ["image"]}) is None
    assert infer_model_type(None) is None
