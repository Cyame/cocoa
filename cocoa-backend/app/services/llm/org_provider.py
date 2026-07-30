"""Helpers for OrganizationProvider ↔ LLMClient (PRD-v3)."""

from __future__ import annotations

import os
import re
from typing import Any

from app.models.organization_provider import OrganizationProvider
from app.services.llm.llm_client import LLMClient, LLMError

# Map request_format → legacy provider_type used by LLMClient dispatch
_FORMAT_TO_PROVIDER_TYPE: dict[str, str] = {
    "completion": "openai-compatible",
    "response": "openai-responses",
    "anthropic": "anthropic",
    "gemini": "gemini",
}

# models.dev npm package hints → request_format
_NPM_TO_FORMAT: dict[str, str] = {
    "@ai-sdk/openai": "completion",
    "@ai-sdk/openai-compatible": "completion",
    "@ai-sdk/azure": "completion",
    "@ai-sdk/anthropic": "anthropic",
    "@ai-sdk/google": "gemini",
    "@ai-sdk/google-vertex": "gemini",
}


def slugify(value: str) -> str:
    """Kebab-case slug from a display name / catalog id."""
    s = value.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "provider"


def infer_request_format(provider_data: dict[str, Any]) -> str:
    """Infer request_format from models.dev provider entry."""
    npm = provider_data.get("npm")
    if isinstance(npm, str) and npm in _NPM_TO_FORMAT:
        return _NPM_TO_FORMAT[npm]
    # Heuristic by id/name
    pid = str(provider_data.get("id") or "").lower()
    name = str(provider_data.get("name") or "").lower()
    blob = f"{pid} {name}"
    if "anthropic" in blob or "claude" in blob:
        return "anthropic"
    if "gemini" in blob or "google" in blob:
        return "gemini"
    if "openai" in blob and "compatible" not in blob:
        return "completion"
    return "completion"


def resolve_api_key(api_key_ref: str) -> str:
    """Resolve API key: env var of that name if set, else treat value as literal key.

    Portal pastes the key directly (URL + key + model). Env-var refs still work
    when the process has that variable set (e.g. ``OPENAI_API_KEY``).
    """
    if not api_key_ref or not api_key_ref.strip():
        raise LLMError(
            "errors.llm.api_key_missing",
            "API key is empty",
        )
    ref = api_key_ref.strip()
    env_val = os.environ.get(ref)
    if env_val:
        return env_val
    return ref


def request_format_to_provider_type(request_format: str) -> str:
    return _FORMAT_TO_PROVIDER_TYPE.get(request_format, "openai-compatible")


def build_llm_client_from_org_provider(
    provider: OrganizationProvider,
    *,
    model: str | None = None,
) -> LLMClient:
    """Materialize an LLMClient from a world OrganizationProvider row."""
    api_key = resolve_api_key(provider.api_key_ref)
    provider_type = request_format_to_provider_type(provider.request_format)
    return LLMClient(
        provider_type=provider_type,
        api_key=api_key,
        base_url=provider.base_url,
        default_model=model or provider.default_model,
        verify_ssl=bool(provider.verify_ssl),
        request_format=provider.request_format,
    )


def models_list_url(provider: OrganizationProvider) -> str:
    """Resolve GET URL for listing models (custom / separate)."""
    if provider.models_endpoint_mode == "separate":
        base = (provider.models_base_url or "").rstrip("/")
        if not base:
            raise ValueError("models_base_url is empty")
        if base.endswith("/models"):
            return base
        return f"{base}/models"
    base = (provider.base_url or "").rstrip("/")
    if not base:
        raise ValueError("base_url is empty")
    return f"{base}/models"


def _models_url_from_parts(
    *,
    base_url: str | None,
    models_endpoint_mode: str,
    models_base_url: str | None,
) -> str:
    if models_endpoint_mode == "separate":
        base = (models_base_url or "").rstrip("/")
        if not base:
            raise ValueError("models_base_url is empty")
        if base.endswith("/models"):
            return base
        return f"{base}/models"
    base = (base_url or "").rstrip("/")
    if not base:
        raise ValueError("base_url is empty")
    return f"{base}/models"


async def fetch_models_from_endpoint(
    *,
    api_key_ref: str,
    base_url: str | None,
    request_format: str,
    verify_ssl: bool = True,
    models_endpoint_mode: str = "inherit",
    models_base_url: str | None = None,
    provider_slug: str = "custom",
) -> tuple[list[dict], str | None]:
    """GET remote /models. Never falls back to models.dev."""
    import httpx

    try:
        api_key = resolve_api_key(api_key_ref)
        url = _models_url_from_parts(
            base_url=base_url,
            models_endpoint_mode=models_endpoint_mode,
            models_base_url=models_base_url,
        )
    except (LLMError, ValueError) as exc:
        return [], str(exc)

    headers: dict[str, str] = {}
    if request_format == "anthropic":
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    else:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(verify=bool(verify_ssl), timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code >= 400:
                return [], f"HTTP {resp.status_code}: {resp.text[:300]}"
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return [], str(exc)

    items: list[dict] = []
    raw_list = data.get("data") if isinstance(data, dict) else data
    if isinstance(raw_list, list):
        for entry in raw_list:
            if isinstance(entry, dict):
                mid = entry.get("id") or entry.get("name")
                if mid:
                    items.append(
                        {
                            "id": str(mid),
                            "name": str(entry.get("name") or mid),
                            "provider": provider_slug,
                            "context_length": entry.get("context_length"),
                        }
                    )
    return items, None


async def fetch_custom_models(
    provider: OrganizationProvider,
) -> tuple[list[dict], str | None]:
    """Return (items, error) for a saved OrganizationProvider row."""
    return await fetch_models_from_endpoint(
        api_key_ref=provider.api_key_ref,
        base_url=provider.base_url,
        request_format=provider.request_format,
        verify_ssl=bool(provider.verify_ssl),
        models_endpoint_mode=provider.models_endpoint_mode,
        models_base_url=provider.models_base_url,
        provider_slug=provider.slug,
    )
