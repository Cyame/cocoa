"""v5.0 builtin 始祖: 5 常驻始祖 + internal zong-jian.

* All 5 始祖 carry a usable ``provider`` config.
* ``zong-jian`` (Director, human) lives in INTERNAL_PRESETS with provider=None.
* Decoding via ``LLMProviderConfig.from_manifest_legacy`` round-trips.
* v5.0 命名波：6 降级神职（唤灵/灵视/衡判/游魂/潜知/百瞳）已移除（v5-rename-decisions §六）。
* v5.1：5 始祖 manifest 均携带 ``subagent_strategy``（6 能力目录白名单内的 enabled 集，
  ``constraints.max_parallel == 4``）；``zong-jian`` 不携带（provider=None，不执行）。
"""

from __future__ import annotations

from app.core.builtin_presets import ALL_BUILTIN_PRESETS, BUILTIN_PRESETS, INTERNAL_PRESETS
from app.schemas.llm import LLMProviderConfig, ProviderType


def test_public_presets_count_and_provider_config():
    assert len(BUILTIN_PRESETS) == 5, "Eyot ships exactly 5 常驻始祖"
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


# v5.1 N1 per-始祖 enabled 矩阵（v5-1-definition.md :49-57）。
_EXPECTED_SUBAGENT_ENABLED: dict[str, list[str]] = {
    "fox": ["intent", "architecture", "research"],
    "beaver": ["explore", "research", "architecture", "quality"],
    "sparrow": ["explore", "quality"],
    "coyote": ["explore", "research", "architecture", "quality"],
    "lion": [
        "intent",
        "architecture",
        "quality",
        "explore",
        "research",
        "vision",
    ],
}


def test_subagent_strategy_matrix_on_ancestors() -> None:
    assert set(_EXPECTED_SUBAGENT_ENABLED) == {p["slug"] for p in BUILTIN_PRESETS}

    for preset in BUILTIN_PRESETS:
        slug = preset["slug"]
        manifest = preset["manifest"]
        strategy = manifest.get("subagent_strategy")
        assert strategy is not None, f"{slug}: missing subagent_strategy"
        assert isinstance(strategy, dict)
        enabled = strategy.get("enabled")
        assert enabled == _EXPECTED_SUBAGENT_ENABLED[slug], (
            f"{slug}: enabled={enabled!r}"
        )
        assert strategy["constraints"]["max_parallel"] == 4

    for preset in INTERNAL_PRESETS:
        assert "subagent_strategy" not in preset["manifest"], (
            f"{preset['slug']}: internal preset must not carry subagent_strategy"
        )
