"""LLM-related Pydantic schemas (P14a).

P14a D12: 4 provider types + unified LLM call wrapper.
P14a D14: backward-compatible manifest decoder — legacy manifests that lack
a ``provider`` field fall back to OpenAI-compatible defaults so P10-era
presets still load without errors.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ProviderType(str, Enum):
    """LLM provider type — determines which SDK + endpoint to dispatch to.

    * ``openai-compatible`` — generic OpenAI chat completions endpoint
      (covers OpenAI itself, Azure, local llama.cpp servers).
    * ``openai-responses`` — OpenAI's newer ``/v1/responses`` endpoint.
    * ``anthropic`` — Anthropic's Claude API (separate SDK).
    * ``custom`` — arbitrary OpenAI-compatible URL; ``base_url`` required.
    """

    openai_compatible = "openai-compatible"
    openai_responses = "openai-responses"
    anthropic = "anthropic"
    custom = "custom"


class LLMProviderConfig(BaseModel):
    """Provider configuration for one LLM client.

    The runtime ``LLMClient`` reads the API key from ``api_key_ref``
    (env-var name, never the secret itself) so config can be safely
    persisted into the database.
    """

    provider_type: ProviderType = ProviderType.openai_compatible
    api_key_ref: str = Field(
        default="OPENAI_API_KEY",
        description="Env var name holding the API key (never the key itself).",
    )
    base_url: str | None = Field(
        default=None,
        description="Custom endpoint URL; required when provider_type is 'custom'.",
    )
    default_model: str = Field(default="gpt-4o-mini")
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)

    @classmethod
    def from_manifest_legacy(cls, manifest: dict[str, Any]) -> "LLMProviderConfig":
        """Decode an BaseClass manifest into a provider config (D14).

        * If ``manifest`` contains a ``provider`` dict → read its fields.
        * Otherwise — legacy P10/P13 manifest → fall back to OpenAI-
          compatible defaults and reuse the legacy ``model`` field.
        """
        if isinstance(manifest.get("provider"), dict):
            p = manifest["provider"]
            return cls(
                provider_type=ProviderType(p.get("type", "openai-compatible")),
                api_key_ref=p.get("api_key_ref", "OPENAI_API_KEY"),
                base_url=p.get("base_url"),
                default_model=p.get("model", "gpt-4o-mini"),
                max_tokens=p.get("max_tokens", 1024),
                temperature=p.get("temperature", 0.7),
            )
        return cls(
            provider_type=ProviderType.openai_compatible,
            api_key_ref="OPENAI_API_KEY",
            default_model=manifest.get("model", "gpt-4o-mini"),
        )


class ModelCatalogEntry(BaseModel):
    """A single model entry from a provider's catalog.

    Mirrors the public surface of ``ModelInfo`` from
    ``app.services.llm.model_catalog`` so API responses can serialise
    catalog items without leaking the internal dataclass.
    """

    id: str
    name: str
    provider: str
    context_length: int | None = None
    pricing: dict[str, Any] | None = None


class LLMResponseSchema(BaseModel):
    """Pydantic twin of ``LLMResponse`` for API responses."""

    content: str
    prompt_tokens: int
    completion_tokens: int
    model: str
    stop_reason: str


class LLMDistillRequest(BaseModel):
    """Request payload for an LLM-assisted ``/distill`` endpoint (P14a).

    ``provider_name`` selects the registered LLMClient; when omitted, the
    endpoint falls back to the heuristic ``AggregatingDistiller`` (no LLM
    call). This keeps P10 callers working unchanged.
    """

    target_skill_slug: str
    source_preset_slug: str
    provider_name: str | None = None


class LLMDistillResult(BaseModel):
    """Response payload for an LLM-assisted ``/distill`` endpoint."""

    new_preset_slug: str
    manifest_preview: dict[str, Any]
    used_llm: bool
