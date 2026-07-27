"""ModelCatalog — fetch LLM model metadata from models.dev with cache + fallback.

P14a references models.dev (https://models.dev/api.json) for a live catalog
of LLM providers + models. We cache for 600s and fall back to a hard-coded
list of common models if the fetch fails (offline / network / rate-limited).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MODELS_DEV_URL = "https://models.dev/api.json"
CACHE_TTL_SECONDS = 600


@dataclass(frozen=True, slots=True)
class ModelInfo:
    """Single model entry."""

    id: str
    name: str
    provider: str
    context_length: int | None = None
    pricing: dict[str, Any] | None = None


# Hard-coded fallback (~20 common models across providers).
_BUILTIN_FALLBACK: list[dict[str, Any]] = [
    {"id": "gpt-4o", "name": "GPT-4o", "provider": "openai", "context_length": 128000},
    {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "provider": "openai", "context_length": 128000},
    {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "provider": "openai", "context_length": 128000},
    {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo", "provider": "openai", "context_length": 16385},
    {"id": "o1-preview", "name": "o1 Preview", "provider": "openai", "context_length": 128000},
    {"id": "o1-mini", "name": "o1 Mini", "provider": "openai", "context_length": 128000},
    {"id": "claude-3-5-sonnet-latest", "name": "Claude 3.5 Sonnet", "provider": "anthropic", "context_length": 200000},
    {"id": "claude-3-5-haiku-latest", "name": "Claude 3.5 Haiku", "provider": "anthropic", "context_length": 200000},
    {"id": "claude-3-opus-latest", "name": "Claude 3 Opus", "provider": "anthropic", "context_length": 200000},
    {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash", "provider": "google", "context_length": 1000000},
    {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro", "provider": "google", "context_length": 2000000},
    {"id": "deepseek-chat", "name": "DeepSeek Chat", "provider": "deepseek", "context_length": 128000},
    {"id": "deepseek-reasoner", "name": "DeepSeek Reasoner", "provider": "deepseek", "context_length": 64000},
    {"id": "qwen2.5-72b-instruct", "name": "Qwen 2.5 72B Instruct", "provider": "alibaba", "context_length": 131072},
    {"id": "llama-3.3-70b-instruct", "name": "Llama 3.3 70B", "provider": "meta", "context_length": 131072},
    {"id": "mistral-large-latest", "name": "Mistral Large", "provider": "mistral", "context_length": 128000},
    {"id": "command-r-plus", "name": "Command R+", "provider": "cohere", "context_length": 128000},
    {"id": "grok-2", "name": "Grok 2", "provider": "xai", "context_length": 131072},
    {"id": "yi-large", "name": "Yi Large", "provider": "zeroone", "context_length": 32768},
    {"id": "moonshot-v1-128k", "name": "Moonshot v1 128k", "provider": "moonshot", "context_length": 131072},
]


def _build_builtin_fallback() -> list[ModelInfo]:
    """Construct ModelInfo list from the hard-coded table."""
    return [ModelInfo(**entry) for entry in _BUILTIN_FALLBACK]


class ModelCatalog:
    """Fetches model list from models.dev with 600s cache + builtin fallback."""

    def __init__(self, ttl_seconds: int = CACHE_TTL_SECONDS) -> None:
        self._cache: list[ModelInfo] | None = None
        self._cache_time: float = 0.0
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()

    async def list_models(self, provider: str | None = None) -> list[ModelInfo]:
        """Return cached or fresh model list. Filter by provider if given."""
        models = await self._get_fresh()
        if provider is not None:
            return [m for m in models if m.provider == provider]
        return models

    def search(self, query: str) -> list[ModelInfo]:
        """Synchronous fuzzy name search across cached models or builtin fallback."""
        if self._cache is None:
            return [
                m
                for m in _build_builtin_fallback()
                if query.lower() in m.name.lower() or query.lower() in m.id.lower()
            ]
        q = query.lower()
        return [m for m in self._cache if q in m.name.lower() or q in m.id.lower()]

    async def _get_fresh(self) -> list[ModelInfo]:
        """Return cached list if fresh; otherwise fetch (with fallback)."""
        now = time.monotonic()
        if self._cache is not None and (now - self._cache_time) < self._ttl:
            return self._cache
        async with self._lock:
            # Re-check inside the lock to avoid a thundering-herd refresh.
            now = time.monotonic()
            if self._cache is not None and (now - self._cache_time) < self._ttl:
                return self._cache
            try:
                models = await self._fetch_from_models_dev()
            except Exception as exc:  # noqa: BLE001 — boundary, fall back below
                logger.warning(
                    "models.dev fetch failed; using builtin fallback",
                    extra={"error": str(exc)},
                )
                models = _build_builtin_fallback()
            self._cache = models
            self._cache_time = time.monotonic()
            return models

    async def _fetch_from_models_dev(self) -> list[ModelInfo]:
        """GET https://models.dev/api.json and parse into ModelInfo list."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(MODELS_DEV_URL)
            response.raise_for_status()
            data = response.json()
        models: list[ModelInfo] = []
        # models.dev schema: {provider_id: {models: {model_id: {...}}, ...}}
        for provider_id, provider_data in data.items():
            if not isinstance(provider_data, dict):
                continue
            models_dict = provider_data.get("models", {})
            if not isinstance(models_dict, dict):
                continue
            for model_id, model_data in models_dict.items():
                if not isinstance(model_data, dict):
                    continue
                limit = model_data.get("limit")
                context = limit.get("context") if isinstance(limit, dict) else None
                models.append(
                    ModelInfo(
                        id=model_id,
                        name=model_data.get("name", model_id),
                        provider=provider_id,
                        context_length=context,
                        pricing=model_data.get("cost"),
                    )
                )
        return models


# Module-level singleton for callers that do not need their own instance.
model_catalog = ModelCatalog()
