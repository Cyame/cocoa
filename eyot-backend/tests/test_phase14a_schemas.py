"""P14a schema tests — LLMProviderConfig.from_manifest_legacy + DTO round-trips.

Single test (per P14a Wave 2 scope): legacy and new manifests both
decode into a valid ``LLMProviderConfig``. Covers:

* Legacy manifest without ``provider`` → defaults + legacy model lift.
* New manifest with full ``provider`` dict → fields respected.
* Empty manifest → pure defaults.

Also performs lightweight round-trip checks for the other DTOs
(``ModelCatalogEntry``, ``LLMResponseSchema``, ``LLMDistillRequest``,
``LLMDistillResult``) so all five schemas stay importable from one
import surface. No DB required.
"""

from __future__ import annotations

from app.schemas.llm import (
    LLMDistillRequest,
    LLMDistillResult,
    LLMProviderConfig,
    LLMResponseSchema,
    ModelCatalogEntry,
    ProviderType,
)


def test_llm_provider_config_from_manifest_legacy():
    """Legacy + new manifests both decode into a valid LLMProviderConfig."""
    # 1. Legacy manifest (no `provider` field) → OpenAI-compatible defaults,
    #    legacy `model` field is lifted into `default_model`.
    legacy_cfg = LLMProviderConfig.from_manifest_legacy(
        {"model": "gpt-3.5-turbo", "prompt": "hi", "skills": []}
    )
    assert legacy_cfg.provider_type == ProviderType.openai_compatible
    assert legacy_cfg.api_key_ref == "OPENAI_API_KEY"
    assert legacy_cfg.base_url is None
    assert legacy_cfg.default_model == "gpt-3.5-turbo"
    assert legacy_cfg.max_tokens == 1024
    assert legacy_cfg.temperature == 0.7

    # 2. Empty manifest → pure defaults (no model lift, no provider field).
    empty_cfg = LLMProviderConfig.from_manifest_legacy({})
    assert empty_cfg.provider_type == ProviderType.openai_compatible
    assert empty_cfg.default_model == "gpt-4o-mini"

    # 3. New manifest with full `provider` dict → all configured values respected.
    new_cfg = LLMProviderConfig.from_manifest_legacy(
        {
            "model": "tbd",
            "prompt": "TODO P14a",
            "provider": {
                "type": "anthropic",
                "model": "claude-3-5-sonnet-latest",
                "api_key_ref": "ANTHROPIC_API_KEY",
                "base_url": "https://api.anthropic.com",
                "max_tokens": 2048,
                "temperature": 0.3,
            },
        }
    )
    assert new_cfg.provider_type == ProviderType.anthropic
    assert new_cfg.api_key_ref == "ANTHROPIC_API_KEY"
    assert new_cfg.base_url == "https://api.anthropic.com"
    assert new_cfg.default_model == "claude-3-5-sonnet-latest"
    assert new_cfg.max_tokens == 2048
    assert new_cfg.temperature == 0.3

    # 4. Round-trip the other DTOs so the import surface stays intact.
    entry = ModelCatalogEntry(
        id="gpt-4o-mini",
        name="GPT-4o Mini",
        provider="openai",
        context_length=128000,
        pricing={"input": 0.15, "output": 0.6},
    )
    assert entry.id == "gpt-4o-mini"
    assert entry.context_length == 128000
    assert entry.pricing == {"input": 0.15, "output": 0.6}

    resp = LLMResponseSchema(
        content="hi", prompt_tokens=10, completion_tokens=5, model="m", stop_reason="stop"
    )
    assert resp.content == "hi" and resp.stop_reason == "stop"

    req = LLMDistillRequest(target_skill_slug="ts", source_preset_slug="sp")
    assert req.provider_name is None  # default = heuristic distiller

    result = LLMDistillResult(
        new_preset_slug="x", manifest_preview={"model": "tbd"}, used_llm=False
    )
    assert result.used_llm is False
