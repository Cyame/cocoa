"""ContentRef scope normalization tests.

These verify the live ``app.core.slash_parser`` behavior: legacy scopes
(``workspace``/``fornix``/``vault``/``memory`` → ``hub``/``instance``) are
normalized to their canonical values, canonical values pass through, and
``blackboard`` is not a parser scope token (normalized on the read path).

The migration-history spot-checks that used to live here (loading the
squashed ``*remap_content_ref_scopes*`` Alembic module) were removed when
the 35 incremental migrations were squashed into the single
``initial schema baseline`` during the Cocoa → Eyot rename.
"""

from __future__ import annotations

import pytest

from app.core.slash_parser import normalize_scope, parse_directive


class TestParserNormalization:
    """parse_directive normalizes legacy scopes and keeps canonical ones."""

    def test_legacy_workspace_normalizes_to_hub(self) -> None:
        result = parse_directive("@workspace:foo/bar /read")
        assert result.content_ref is not None
        assert result.content_ref.scope == "hub"

    def test_legacy_workspace_path_preserved(self) -> None:
        """Path after the scope survives (slash-free path avoids /cmd extraction)."""
        result = parse_directive("/read @workspace:foo.md")
        assert result.content_ref is not None
        assert result.content_ref.scope == "hub"
        assert result.content_ref.path == "foo.md"

    def test_legacy_memory_normalizes_to_instance(self) -> None:
        result = parse_directive("/read @memory")
        assert result.content_ref is not None
        assert result.content_ref.scope == "instance"

    def test_canonical_hub_passes_through(self) -> None:
        result = parse_directive("/read @hub:x")
        assert result.content_ref is not None
        assert result.content_ref.scope == "hub"
        assert result.content_ref.path == "x"

    def test_canonical_instance_passes_through(self) -> None:
        result = parse_directive("/read @instance:y")
        assert result.content_ref is not None
        assert result.content_ref.scope == "instance"
        assert result.content_ref.path == "y"

    def test_all_legacy_scopes_normalize(self) -> None:
        cases = {
            "workspace": "hub",
            "fornix": "hub",
            "vault": "hub",
            "memory": "instance",
        }
        for legacy, canonical in cases.items():
            result = parse_directive(f"/read @{legacy}:p")
            assert result.content_ref is not None, legacy
            assert result.content_ref.scope == canonical, legacy

    def test_blackboard_not_a_parse_scope(self) -> None:
        """``blackboard`` is not a parser scope token (per spec) — stays in args.

        The parser recognizes only ``hub|instance|workspace|fornix|vault|memory``.
        ``blackboard`` is handled on the read path by ``normalize_scope`` /
        the schema validator / the JSONB migration instead.
        """
        result = parse_directive("/read @blackboard:p")
        assert result.content_ref is None
        assert "@blackboard:p" in result.args

    def test_normalize_scope_helper(self) -> None:
        assert normalize_scope("workspace") == "hub"
        assert normalize_scope("fornix") == "hub"
        assert normalize_scope("vault") == "hub"
        assert normalize_scope("blackboard") == "hub"
        assert normalize_scope("memory") == "instance"
        assert normalize_scope("hub") == "hub"
        assert normalize_scope("instance") == "instance"
        assert normalize_scope("unknown") == "unknown"

@pytest.mark.parametrize(
    ("legacy", "canonical"),
    [
        ("workspace", "hub"),
        ("fornix", "hub"),
        ("vault", "hub"),
        ("blackboard", "hub"),
        ("memory", "instance"),
    ],
)
def test_normalize_scope_table_driven(legacy: str, canonical: str) -> None:
    assert normalize_scope(legacy) == canonical
