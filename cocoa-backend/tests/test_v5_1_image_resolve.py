"""v5.1 N2 镜像解析：``deploy_service._resolve_instance_image`` 单测。

* 5 大始祖 slug → ``{registry}/cocoa-instance-{slug}:{version}``
* 自定义 slug / None → ``cocoa-instance-base``（G9 回退）
* ``image_version`` 缺省/None → ``ENGINE_VERSION``（0.83.0）
* registry 前缀取 ``COCOA_INSTANCE_REGISTRY``（默认 localhost:5000）；
  空串 → 无前缀（v5-1-definition.md :90）。
"""

from __future__ import annotations

import pytest

from app.services.deploy_service import ENGINE_VERSION, _resolve_instance_image

_ANCESTOR_SLUGS = ("fox", "beaver", "sparrow", "coyote", "lion")


@pytest.fixture(autouse=True)
def _clear_registry_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COCOA_INSTANCE_REGISTRY", raising=False)


def test_ancestor_slugs_resolve_to_slugged_images() -> None:
    for slug in _ANCESTOR_SLUGS:
        assert _resolve_instance_image(slug, "v1.0") == (
            f"localhost:5000/cocoa-instance-{slug}:v1.0"
        )


def test_ancestor_slugs_default_to_engine_version() -> None:
    for slug in _ANCESTOR_SLUGS:
        assert _resolve_instance_image(slug, None) == (
            f"localhost:5000/cocoa-instance-{slug}:{ENGINE_VERSION}"
        )


def test_custom_slug_falls_back_to_base_image() -> None:
    assert _resolve_instance_image("custom-clerk", "v1.0") == (
        "localhost:5000/cocoa-instance-base:v1.0"
    )


def test_none_slug_falls_back_to_base_image() -> None:
    assert _resolve_instance_image(None, None) == (
        f"localhost:5000/cocoa-instance-base:{ENGINE_VERSION}"
    )


def test_empty_image_version_defaults_to_engine_version() -> None:
    assert _resolve_instance_image("fox", "") == (
        f"localhost:5000/cocoa-instance-fox:{ENGINE_VERSION}"
    )


def test_explicit_image_version_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COCOA_INSTANCE_REGISTRY", "registry.example.com")
    assert _resolve_instance_image("beaver", "v9.9") == (
        "registry.example.com/cocoa-instance-beaver:v9.9"
    )


def test_registry_env_overrides_default_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COCOA_INSTANCE_REGISTRY", "registry.example.com")
    assert _resolve_instance_image("fox", None) == (
        f"registry.example.com/cocoa-instance-fox:{ENGINE_VERSION}"
    )


def test_registry_env_strips_whitespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COCOA_INSTANCE_REGISTRY", "  registry.example.com  ")
    assert _resolve_instance_image("lion", "v1.0") == (
        "registry.example.com/cocoa-instance-lion:v1.0"
    )


def test_empty_registry_omits_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COCOA_INSTANCE_REGISTRY", "")
    assert _resolve_instance_image("fox", "v1.0") == "cocoa-instance-fox:v1.0"
    assert _resolve_instance_image("custom", "v1.0") == (
        "cocoa-instance-base:v1.0"
    )
