"""ProviderRouter — multi-provider LLMClient registry.

P14a allows multiple provider configs to be registered by name; get_client(name)
returns a cached LLMClient instance.
"""

from __future__ import annotations

import logging

from app.services.llm.llm_client import LLMClient

logger = logging.getLogger(__name__)


class ProviderNotFoundError(Exception):
    """Raised when get_client() is called with an unknown provider name."""

    def __init__(self, name: str):
        super().__init__(f"Provider not registered: {name!r}")
        self.name = name


class ProviderRouter:
    """Registry of LLMClient instances keyed by provider name."""

    def __init__(self):
        self._configs: dict[str, dict] = {}
        self._clients: dict[str, LLMClient] = {}

    def register(
        self,
        name: str,
        provider_type: str,
        api_key: str,
        base_url: str | None = None,
        default_model: str = "gpt-4o-mini",
    ) -> None:
        """Register a provider config. Lazy-instantiate LLMClient on first get."""
        if name in self._configs:
            logger.warning("Provider %r already registered; overwriting config", name)
        self._configs[name] = {
            "provider_type": provider_type,
            "api_key": api_key,
            "base_url": base_url,
            "default_model": default_model,
        }
        # Invalidate any cached client
        self._clients.pop(name, None)

    def get_client(self, provider_name: str) -> LLMClient:
        """Return cached LLMClient or instantiate from config."""
        if provider_name not in self._configs:
            raise ProviderNotFoundError(provider_name)
        if provider_name not in self._clients:
            cfg = self._configs[provider_name]
            self._clients[provider_name] = LLMClient(
                provider_type=cfg["provider_type"],
                api_key=cfg["api_key"],
                base_url=cfg["base_url"],
                default_model=cfg["default_model"],
            )
        return self._clients[provider_name]

    def list_providers(self) -> list[str]:
        """Return sorted list of registered provider names."""
        return sorted(self._configs.keys())

    def has_provider(self, name: str) -> bool:
        return name in self._configs

    def unregister(self, name: str) -> None:
        """Remove a provider. No-op if not present."""
        self._configs.pop(name, None)
        self._clients.pop(name, None)


# Module-level default router for convenient access
default_router = ProviderRouter()
