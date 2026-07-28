"""P14a builtin-presets upgrade tests — every preset carries a valid provider config.

Single test (per P14a Wave 2 scope):

* All 6 presets carry a ``provider`` field on their manifest.
* Non-human presets expose a provider dict with ``type`` and ``model``.
* ``zong-jian`` (Director, human) keeps ``provider=None``.
* Decoding each preset via ``LLMProviderConfig.from_manifest_legacy``
  round-trips without raising (D14 backward compat exercised on real data).

No DB required.
"""

from __future__ import annotations

from app.core.builtin_presets import BUILTIN_PRESETS
from app.schemas.llm import LLMProviderConfig, ProviderType


def test_all_presets_have_valid_provider_config():
    """All 6 builtin presets carry a usable provider config (P14a)."""
    assert len(BUILTIN_PRESETS) == 6, "Cocoa ships exactly 6 builtin presets"

    expected_types = {
        "mi-shi": ProviderType.openai_compatible,
        "zhu-jin": ProviderType.openai_compatible,
        "ling-shi": ProviderType.anthropic,
        "you-hun": ProviderType.openai_compatible,
        "heng-pan": ProviderType.anthropic,
        "zong-jian": None,  # human-driven; no LLM
    }

    for preset in BUILTIN_PRESETS:
        slug = preset["slug"]
        manifest = preset["manifest"]
        assert "provider" in manifest, f"{slug}: missing `provider` field"
        provider = manifest["provider"]

        if slug == "zong-jian":
            # Director is human; provider must be explicitly None.
            assert provider is None, f"{slug}: human preset must have provider=None"
            continue

        # Non-human presets must carry a dict with required keys.
        assert isinstance(provider, dict), f"{slug}: provider must be a dict, got {type(provider).__name__}"
        assert "type" in provider, f"{slug}: provider dict missing 'type'"
        assert "model" in provider, f"{slug}: provider dict missing 'model'"
        assert provider["model"] != "tbd", f"{slug}: provider.model must be a real model id, not 'tbd'"
        assert ProviderType(provider["type"]) == expected_types[slug], (
            f"{slug}: expected provider type {expected_types[slug].value}, "
            f"got {provider['type']!r}"
        )

        # Round-trip through LLMProviderConfig.from_manifest_legacy to ensure
        # the D14 decoder accepts the new manifest format end-to-end.
        cfg = LLMProviderConfig.from_manifest_legacy(manifest)
        assert cfg.provider_type == expected_types[slug]
        assert cfg.default_model == provider["model"]
        assert cfg.max_tokens == provider.get("max_tokens", 1024)
        assert cfg.temperature == provider.get("temperature", 0.7)

    # Manifest invariants that P14a must preserve.
    for preset in BUILTIN_PRESETS:
        assert preset["version"] == "1.0.0", f"{preset['slug']}: version must stay 1.0.0"
        prompt = preset["manifest"]["prompt"]
        assert prompt and prompt != "TODO P14a", (
            f"{preset['slug']}: prompt must be a real system prompt, not the 'TODO P14a' placeholder"
        )
        assert len(prompt) >= 80, (
            f"{preset['slug']}: prompt too short ({len(prompt)} chars); expected at least 80"
        )
