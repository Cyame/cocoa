"""PRD-v3-post builtin 神职: 11 public presets + internal zong-jian.

* All public presets carry a usable ``provider`` config.
* ``zong-jian`` (Director, human) lives in INTERNAL_PRESETS with provider=None.
* Decoding via ``LLMProviderConfig.from_manifest_legacy`` round-trips.
"""

from __future__ import annotations

from app.core.builtin_presets import ALL_BUILTIN_PRESETS, BUILTIN_PRESETS, INTERNAL_PRESETS
from app.schemas.llm import LLMProviderConfig, ProviderType


def test_public_presets_count_and_provider_config():
    assert len(BUILTIN_PRESETS) == 11, "Cocoa ships exactly 11 public 神职"
    assert len(INTERNAL_PRESETS) == 1
    assert INTERNAL_PRESETS[0]["slug"] == "zong-jian"
    assert "internal" in (INTERNAL_PRESETS[0].get("tags") or [])

    expected_types = {
        "mi-shi": ProviderType.openai_compatible,
        "huan-ling": ProviderType.openai_compatible,
        "an-xing": ProviderType.anthropic,
        "an-ying": ProviderType.openai_compatible,
        "zhu-jin": ProviderType.openai_compatible,
        "ling-shi": ProviderType.anthropic,
        "heng-pan": ProviderType.anthropic,
        "you-hun": ProviderType.openai_compatible,
        "qian-zhi": ProviderType.openai_compatible,
        "bai-tong": ProviderType.openai_compatible,
        "jiu-ri": ProviderType.anthropic,
    }

    for preset in BUILTIN_PRESETS:
        slug = preset["slug"]
        manifest = preset["manifest"]
        assert "provider" in manifest, f"{slug}: missing `provider` field"
        provider = manifest["provider"]
        assert isinstance(provider, dict), f"{slug}: provider must be a dict"
        assert "type" in provider and "model" in provider
        assert provider["model"] != "tbd"
        assert ProviderType(provider["type"]) == expected_types[slug]
        assert preset.get("description"), f"{slug}: missing description"
        assert preset.get("tags"), f"{slug}: missing tags"

        cfg = LLMProviderConfig.from_manifest_legacy(manifest)
        assert cfg.provider_type == expected_types[slug]
        assert cfg.default_model == provider["model"]

        prompt = manifest["prompt"]
        assert prompt and len(prompt) >= 40

    zong = INTERNAL_PRESETS[0]
    assert zong["manifest"]["provider"] is None
    assert len(ALL_BUILTIN_PRESETS) == 12
