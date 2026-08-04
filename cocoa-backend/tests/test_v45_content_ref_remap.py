"""v4.5 ContentRef scope remap tests (H7).

Covers three layers of the ContentRef ``hub | instance`` migration:

1. Parser normalization — ``app.core.slash_parser`` accepts legacy scopes
   (``workspace``/``fornix``/``vault``/``memory`` → ``hub``/``instance``)
   and passes the canonical values through.  ``blackboard`` is not a parser
   scope token (per spec) — it is normalized on the read path by
   ``normalize_scope`` / the schema validator / the JSONB migration.
2. Migration helper ``_remap_scope`` — pure recursive JSON remap, including
   the audit M2 nested/non-uniform payload shapes.
3. DB spot-check — 25 ``events.payload`` rows are remapped by the
   migration's ``_remap_events_payloads`` against a real Postgres test DB:
   21 legacy-scope rows carrying 31 legacy scope values (flat + nested per
   audit M2) plus 4 hub/instance/system passthrough controls.  After the
   remap, 0 legacy scope values remain and the control values are preserved.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text

from app.core.slash_parser import normalize_scope, parse_directive

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_MIGRATION_FILES = sorted(
    (_BACKEND_DIR / "alembic" / "versions").glob("*remap_content_ref_scopes*")
)
assert len(_MIGRATION_FILES) == 1, f"expected exactly one remap migration, got {_MIGRATION_FILES}"
_MIGRATION_PATH = _MIGRATION_FILES[0]

_spec = importlib.util.spec_from_file_location("v45_remap_migration", _MIGRATION_PATH)
assert _spec is not None and _spec.loader is not None
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

LEGACY = {"workspace", "fornix", "vault", "memory", "blackboard"}


def _count_legacy_scopes(payload: object) -> int:
    """Count ``scope`` dict values that are still legacy strings, recursively."""
    if isinstance(payload, dict):
        n = 0
        for key, value in payload.items():
            if key == "scope" and isinstance(value, str) and value in LEGACY:
                n += 1
            n += _count_legacy_scopes(value)
        return n
    if isinstance(payload, list):
        return sum(_count_legacy_scopes(item) for item in payload)
    return 0


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


class TestRemapScopeHelper:
    """Pure recursive JSON remap — flat, nested, and passthrough shapes."""

    def test_flat_legacy_scope_remapped(self) -> None:
        assert _migration._remap_scope({"scope": "workspace"}) == {"scope": "hub"}
        assert _migration._remap_scope({"scope": "memory"}) == {"scope": "instance"}

    def test_nested_content_ref_remapped(self) -> None:
        payload = {"content_ref": {"scope": "fornix", "path": "docs/spec.md"}}
        assert _migration._remap_scope(payload) == {
            "content_ref": {"scope": "hub", "path": "docs/spec.md"}
        }

    def test_audit_m2_non_uniform_shapes(self) -> None:
        """Nested dicts + lists, multiple scopes, mixed depths (audit M2)."""
        payload = {
            "directives": [
                {"scope": "vault", "path": "a"},
                {"scope": "blackboard", "path": "b"},
            ],
            "meta": {"refs": {"scope": "memory", "items": [{"scope": "workspace"}]}},
            "unrelated": {"scope": "system"},  # non-legacy value passes through
        }
        remapped = _migration._remap_scope(payload)
        assert _count_legacy_scopes(remapped) == 0
        assert remapped["directives"][0]["scope"] == "hub"
        assert remapped["directives"][1]["scope"] == "hub"
        assert remapped["meta"]["refs"]["scope"] == "instance"
        assert remapped["meta"]["refs"]["items"][0]["scope"] == "hub"
        assert remapped["unrelated"]["scope"] == "system"

    def test_canonical_and_non_string_values_pass_through(self) -> None:
        payload = {"scope": "hub", "nested": {"scope": "instance"}, "count": 3}
        assert _migration._remap_scope(payload) == payload


# 21 legacy payloads (flat + audit-M2 nested shapes) carrying 31 legacy
# scope values total, plus 4 hub/instance/system passthrough controls.
_LEGACY_PAYLOADS: list[dict] = [
    {"scope": "workspace"},
    {"scope": "fornix"},
    {"scope": "vault"},
    {"scope": "memory"},
    {"scope": "blackboard"},
]
_LEGACY_PAYLOADS += [
    {"content_ref": {"scope": "workspace", "path": f"docs/{i}.md"}} for i in range(5)
]
_LEGACY_PAYLOADS += [
    {"refs": [{"scope": "fornix"}, {"scope": "vault", "path": "a"}]},
    {"meta": {"nested": {"scope": "memory", "tags": [{"scope": "workspace"}]}}},
    {"directives": [{"scope": "blackboard", "path": "x"}, {"scope": "memory"}]},
    {"list_of_refs": [{"scope": "vault"}, {"scope": "vault"}, {"scope": "memory"}]},
    {
        "content_ref": {"scope": "workspace", "path": "notes/a.md"},
        "extra": {"scope": "fornix"},
    },
    {"scope": "workspace", "nested": [{"scope": "memory"}, {"scope": "vault"}]},
    {"outer": {"scope": "blackboard", "inner": {"scope": "workspace"}}},
    {"scope": "fornix"},
    {"scope": "memory", "path": "lesson:x"},
    {"refs": [{"scope": "workspace"}, {"scope": "blackboard"}]},
    {"deep": {"deeper": {"deepest": {"scope": "vault"}}}},
]
_TOTAL_LEGACY_VALUES = sum(_count_legacy_scopes(p) for p in _LEGACY_PAYLOADS)

_CONTROL_PAYLOADS: list[dict] = [
    {"scope": "hub"},
    {"scope": "instance"},
    {"scope": "system"},
    {"refs": [{"scope": "hub"}, {"scope": "instance", "path": "p"}]},
]


class TestMigrationEventsSpotCheck:
    """DB spot-check: run the migration's remap against a real test DB.

    Spot-check row count: 25 ``events`` rows — 21 legacy payloads carrying
    31 legacy scope values (workspace/fornix/vault/memory/blackboard mixed,
    nested per audit M2) plus 4 hub/instance/system passthrough controls.
    After ``_remap_events_payloads`` runs, 0 legacy scope values remain and
    the control values are preserved.
    """

    async def test_migration_remaps_events_payloads(self, session) -> None:
        from app.models.event import Event

        for payload in _LEGACY_PAYLOADS + _CONTROL_PAYLOADS:
            session.add(
                Event(type="test.content_ref_remap", actor_type="system", payload=payload)
            )
        await session.commit()

        rows = (await session.execute(text("SELECT payload FROM events"))).scalars().all()
        assert len(rows) == len(_LEGACY_PAYLOADS) + len(_CONTROL_PAYLOADS)
        assert sum(_count_legacy_scopes(r) for r in rows) == _TOTAL_LEGACY_VALUES

        async with session.bind.connect() as conn:
            updated = await conn.run_sync(_migration._remap_events_payloads)
            await conn.commit()

        assert updated == len(_LEGACY_PAYLOADS)

        after = (await session.execute(text("SELECT payload FROM events"))).scalars().all()
        assert len(after) == len(_LEGACY_PAYLOADS) + len(_CONTROL_PAYLOADS)
        assert all(_count_legacy_scopes(r) == 0 for r in after), "legacy scope values remain"

        scope_values = {v for row in after for v in _iter_scope_values(row)}
        assert scope_values == {"hub", "instance", "system"}


def _iter_scope_values(payload: object) -> set[str]:
    """Yield every ``scope`` dict value in a nested JSON structure."""
    out: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key == "scope" and isinstance(value, str):
                out.add(value)
            out |= _iter_scope_values(value)
    elif isinstance(payload, list):
        for item in payload:
            out |= _iter_scope_values(item)
    return out


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
