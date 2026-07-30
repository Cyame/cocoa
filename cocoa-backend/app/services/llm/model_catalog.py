"""ModelCatalog — models.dev fetch with bundled offline snapshot (PRD-v3)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.services.llm.org_provider import infer_request_format

logger = logging.getLogger(__name__)

MODELS_DEV_URL = "https://models.dev/api.json"
# Long TTL: portal does not need a live-fresh catalog every open.
CACHE_TTL_SECONDS = 7 * 24 * 3600
# Bundled snapshot for demos / offline (committed under app/resources/).
BUNDLED_MODELS_DEV_PATH = (
    Path(__file__).resolve().parents[2] / "resources" / "models_dev_api.json"
)


@dataclass(frozen=True, slots=True)
class ModelInfo:
    """Single model entry."""

    id: str
    name: str
    provider: str
    context_length: int | None = None
    pricing: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ProviderInfo:
    """models.dev provider preset (not a DB row)."""

    id: str
    name: str
    api: str | None
    inferred_request_format: str
    model_count: int
    doc: str | None
    raw: dict[str, Any]


_BUILTIN_FALLBACK: list[dict[str, Any]] = [
    {"id": "gpt-4o", "name": "GPT-4o", "provider": "openai", "context_length": 128000},
    {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "provider": "openai", "context_length": 128000},
    {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "provider": "openai", "context_length": 128000},
    {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo", "provider": "openai", "context_length": 16385},
    {"id": "o1-preview", "name": "o1 Preview", "provider": "openai", "context_length": 128000},
    {"id": "o1-mini", "name": "o1 Mini", "provider": "openai", "context_length": 128000},
    {
        "id": "claude-3-5-sonnet-latest",
        "name": "Claude 3.5 Sonnet",
        "provider": "anthropic",
        "context_length": 200000,
    },
    {
        "id": "claude-3-5-haiku-latest",
        "name": "Claude 3.5 Haiku",
        "provider": "anthropic",
        "context_length": 200000,
    },
    {
        "id": "claude-3-opus-latest",
        "name": "Claude 3 Opus",
        "provider": "anthropic",
        "context_length": 200000,
    },
    {
        "id": "gemini-2.0-flash",
        "name": "Gemini 2.0 Flash",
        "provider": "google",
        "context_length": 1000000,
    },
    {
        "id": "gemini-1.5-pro",
        "name": "Gemini 1.5 Pro",
        "provider": "google",
        "context_length": 2000000,
    },
    {
        "id": "deepseek-chat",
        "name": "DeepSeek Chat",
        "provider": "deepseek",
        "context_length": 128000,
    },
    {
        "id": "deepseek-reasoner",
        "name": "DeepSeek Reasoner",
        "provider": "deepseek",
        "context_length": 64000,
    },
    {
        "id": "qwen2.5-72b-instruct",
        "name": "Qwen 2.5 72B Instruct",
        "provider": "alibaba",
        "context_length": 131072,
    },
    {
        "id": "llama-3.3-70b-instruct",
        "name": "Llama 3.3 70B",
        "provider": "meta",
        "context_length": 131072,
    },
    {
        "id": "mistral-large-latest",
        "name": "Mistral Large",
        "provider": "mistral",
        "context_length": 128000,
    },
    {
        "id": "command-r-plus",
        "name": "Command R+",
        "provider": "cohere",
        "context_length": 128000,
    },
    {"id": "grok-2", "name": "Grok 2", "provider": "xai", "context_length": 131072},
    {"id": "yi-large", "name": "Yi Large", "provider": "zeroone", "context_length": 32768},
    {
        "id": "moonshot-v1-128k",
        "name": "Moonshot v1 128k",
        "provider": "moonshot",
        "context_length": 131072,
    },
]

_BUILTIN_PROVIDERS: list[dict[str, Any]] = [
    {
        "id": "openai",
        "name": "OpenAI",
        "api": "https://api.openai.com/v1",
        "npm": "@ai-sdk/openai",
    },
    {
        "id": "anthropic",
        "name": "Anthropic",
        "api": "https://api.anthropic.com",
        "npm": "@ai-sdk/anthropic",
    },
    {
        "id": "google",
        "name": "Google",
        "api": "https://generativelanguage.googleapis.com/v1beta",
        "npm": "@ai-sdk/google",
    },
]


def _build_builtin_fallback() -> list[ModelInfo]:
    return [ModelInfo(**entry) for entry in _BUILTIN_FALLBACK]


def _providers_from_raw(
    data: dict[str, Any],
) -> list[ProviderInfo]:
    providers: list[ProviderInfo] = []
    for provider_id, provider_data in data.items():
        if not isinstance(provider_data, dict):
            continue
        models_dict = provider_data.get("models") or {}
        model_count = len(models_dict) if isinstance(models_dict, dict) else 0
        enriched = {**provider_data, "id": provider_id}
        providers.append(
            ProviderInfo(
                id=provider_id,
                name=str(provider_data.get("name") or provider_id),
                api=provider_data.get("api"),
                inferred_request_format=infer_request_format(enriched),
                model_count=model_count,
                doc=provider_data.get("doc"),
                raw=enriched,
            )
        )
    return providers


def _builtin_provider_infos() -> list[ProviderInfo]:
    by_provider: dict[str, int] = {}
    for m in _BUILTIN_FALLBACK:
        by_provider[m["provider"]] = by_provider.get(m["provider"], 0) + 1
    out: list[ProviderInfo] = []
    for p in _BUILTIN_PROVIDERS:
        enriched = {**p}
        out.append(
            ProviderInfo(
                id=p["id"],
                name=p["name"],
                api=p.get("api"),
                inferred_request_format=infer_request_format(enriched),
                model_count=by_provider.get(p["id"], 0),
                doc=None,
                raw=enriched,
            )
        )
    return out


class ModelCatalog:
    """Fetches models.dev with long TTL; falls back to bundled snapshot then builtin."""

    def __init__(self, ttl_seconds: int = CACHE_TTL_SECONDS) -> None:
        self._cache: list[ModelInfo] | None = None
        self._provider_cache: list[ProviderInfo] | None = None
        self._raw_cache: dict[str, Any] | None = None
        self._cache_time: float = 0.0
        self._degraded: bool = False
        self._source: str = "empty"
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()

    @property
    def degraded(self) -> bool:
        return self._degraded

    @property
    def source(self) -> str:
        """active | bundled | builtin | empty"""
        return self._source

    async def list_models(self, provider: str | None = None) -> list[ModelInfo]:
        models = await self._get_fresh()
        if provider is not None:
            return [m for m in models if m.provider == provider]
        return models

    async def list_providers(self, q: str | None = None) -> tuple[list[ProviderInfo], bool]:
        await self._get_fresh()
        providers = self._provider_cache or _builtin_provider_infos()
        if q:
            ql = q.lower()
            providers = [
                p
                for p in providers
                if ql in p.id.lower() or ql in p.name.lower()
            ]
        return providers, self._degraded

    async def get_provider(self, catalog_provider_id: str) -> ProviderInfo | None:
        providers, _ = await self.list_providers()
        for p in providers:
            if p.id == catalog_provider_id:
                return p
        return None

    async def list_models_for_catalog_provider(
        self, catalog_provider_id: str
    ) -> tuple[list[ModelInfo], bool]:
        models = await self.list_models(provider=catalog_provider_id)
        return models, self._degraded

    def search(self, query: str) -> list[ModelInfo]:
        if self._cache is None:
            return [
                m
                for m in _build_builtin_fallback()
                if query.lower() in m.name.lower() or query.lower() in m.id.lower()
            ]
        q = query.lower()
        return [m for m in self._cache if q in m.name.lower() or q in m.id.lower()]

    def _apply_raw(self, raw: dict[str, Any], *, source: str, degraded: bool) -> list[ModelInfo]:
        models = self._parse_models(raw)
        providers = _providers_from_raw(raw)
        self._degraded = degraded
        self._source = source
        self._raw_cache = raw
        self._cache = models
        self._provider_cache = providers
        self._cache_time = time.monotonic()
        return models

    def _load_bundled_raw(self) -> dict[str, Any] | None:
        path = BUNDLED_MODELS_DEV_PATH
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "bundled models.dev snapshot unreadable",
                extra={"path": str(path), "error": str(exc)},
            )
            return None
        if not isinstance(data, dict) or not data:
            return None
        return data

    async def _get_fresh(self) -> list[ModelInfo]:
        now = time.monotonic()
        if self._cache is not None and (now - self._cache_time) < self._ttl:
            return self._cache
        async with self._lock:
            now = time.monotonic()
            if self._cache is not None and (now - self._cache_time) < self._ttl:
                return self._cache
            try:
                raw = await self._fetch_raw()
                return self._apply_raw(raw, source="live", degraded=False)
            except Exception as exc:  # noqa: BLE001
                # Keep a previously successful in-memory cache if present.
                if self._cache is not None and self._provider_cache is not None:
                    logger.warning(
                        "models.dev fetch failed; keeping stale cache",
                        extra={"error": str(exc), "source": self._source},
                    )
                    self._degraded = True
                    self._cache_time = time.monotonic()
                    return self._cache

                bundled = self._load_bundled_raw()
                if bundled is not None:
                    logger.warning(
                        "models.dev fetch failed; using bundled snapshot",
                        extra={"error": str(exc), "path": str(BUNDLED_MODELS_DEV_PATH)},
                    )
                    return self._apply_raw(bundled, source="bundled", degraded=True)

                logger.warning(
                    "models.dev fetch failed; using builtin fallback",
                    extra={"error": str(exc)},
                )
                models = _build_builtin_fallback()
                providers = _builtin_provider_infos()
                self._degraded = True
                self._source = "builtin"
                self._raw_cache = None
                self._cache = models
                self._provider_cache = providers
                self._cache_time = time.monotonic()
                return models

    async def _fetch_raw(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(MODELS_DEV_URL)
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict):
            raise ValueError("models.dev response is not an object")
        return data

    def _parse_models(self, data: dict[str, Any]) -> list[ModelInfo]:
        models: list[ModelInfo] = []
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


model_catalog = ModelCatalog()
