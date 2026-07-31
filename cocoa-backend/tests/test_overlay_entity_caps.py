"""Overlay + world-hub prompt scaffold semantics."""

from __future__ import annotations

from types import SimpleNamespace

from app.core.overlay import resolve_entity_config
from app.core.prompt_compose import build_prompt_scaffold


def test_capabilities_and_genes_are_entity_only() -> None:
    entity = SimpleNamespace(
        slug="alice",
        name="Alice",
        display_name="Alice",
        system_prompt=None,
        config_override=None,
        capabilities=["cap-a", "cap-b"],
        preset_slug="clerk",
    )
    base = {
        "system_prompt": "Base operating form",
        "default_capabilities": ["base-only-cap"],
        "default_gene_refs": ["base-gene"],
        "default_model": "gpt-4o-mini",
        "skills": ["should-not-leak"],
    }
    cfg = resolve_entity_config(entity, base)  # type: ignore[arg-type]
    assert cfg["system_prompt"] == "Base operating form"
    assert cfg["default_capabilities"] == ["cap-a", "cap-b"]
    assert cfg["default_gene_refs"] == []
    assert "base-only-cap" not in cfg["default_capabilities"]
    assert "base-gene" not in cfg["default_gene_refs"]


def test_entity_gene_refs_from_override_only() -> None:
    entity = SimpleNamespace(
        slug="bob",
        name="Bob",
        display_name=None,
        system_prompt="Entity role",
        config_override={"default_gene_refs": ["g1"], "default_model": "x"},
        capabilities=[],
        preset_slug="clerk",
    )
    cfg = resolve_entity_config(
        entity,  # type: ignore[arg-type]
        {"system_prompt": "Base", "default_gene_refs": ["base-g"], "default_capabilities": ["bc"]},
    )
    assert cfg["system_prompt"] == "Entity role"
    assert cfg["default_gene_refs"] == ["g1"]
    assert cfg["default_capabilities"] == []
    assert cfg["default_model"] == "x"


def test_scaffold_separates_template_and_entity_caps() -> None:
    text = build_prompt_scaffold(
        {
            "baseclass_name": "书记",
            "baseclass_template_prompt": "模板思维",
            "entity_name": "小艾",
            "entity_role_prompt": "负责会议纪要",
            "default_capabilities": ["note-taking"],
            "default_gene_refs": [],
        }
    )
    assert "静态模板" in text or "神职" in text
    assert "小艾" in text
    assert "note-taking" in text
    assert "负责会议纪要" in text
