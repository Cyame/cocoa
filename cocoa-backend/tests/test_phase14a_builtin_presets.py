"""v5.0 builtin 始祖: 5 常驻始祖 + internal zong-jian.

* All 5 始祖 carry a usable ``provider`` config.
* ``zong-jian`` (Director, human) lives in INTERNAL_PRESETS with provider=None.
* Decoding via ``LLMProviderConfig.from_manifest_legacy`` round-trips.
* v5.0 命名波：6 降级神职（唤灵/灵视/衡判/游魂/潜知/百瞳）已移除（v5-rename-decisions §六）。
"""

from __future__ import annotations

from app.core.builtin_presets import ALL_BUILTIN_PRESETS, BUILTIN_PRESETS, INTERNAL_PRESETS
from app.schemas.llm import LLMProviderConfig, ProviderType


def test_public_presets_count_and_provider_config():
    assert len(BUILTIN_PRESETS) == 5, "Cocoa ships exactly 5 常驻始祖"
    assert len(INTERNAL_PRESETS) == 1
    assert INTERNAL_PRESETS[0]["slug"] == "zong-jian"
    assert "internal" in (INTERNAL_PRESETS[0].get("tags") or [])

    expected_types = {
        "fox": ProviderType.openai_compatible,
        "beaver": ProviderType.anthropic,
        "sparrow": ProviderType.openai_compatible,
        "coyote": ProviderType.openai_compatible,
        "lion": ProviderType.anthropic,
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
    assert len(ALL_BUILTIN_PRESETS) == 6
