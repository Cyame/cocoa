"""Unit tests for the migration-hash helper.

The migration hash is the source of truth for "is this instance still in
sync with the entity". Once defined, the formula must never change
silently — otherwise existing ``migration_hash`` values stored on
``employees`` and ``active_hash`` values stored on ``instances`` would
stop comparing correctly.

These tests cover the determinism + format contract of the helper.
Integration behaviour (effect on Entity / Instance rows) is covered by
the API endpoint tests in ``tests/api/v1/test_learning_actions.py``.
"""

from __future__ import annotations

import hashlib

import pytest

from app.core.migration_hash import (
    compute_employee_migration_hash,
    compute_migration_hash,
)
from app.models.employee import Employee


def _caps(*names: str) -> list[dict]:
    """Build a capabilities list with deterministic ordering."""
    return [
        {"name": n, "type": "skill", "description": n, "source": "promote"}
        for n in sorted(names)
    ]


class TestComputeMigrationHash:
    """Direct tests of the hash function."""

    def test_empty_inputs_produce_64_hex_chars(self) -> None:
        """Empty capabilities + empty prompt produces a stable 64-char hex digest."""
        h = compute_migration_hash([], "")
        assert len(h) == 64
        int(h, 16)  # raises if not hex

    def test_none_inputs_align_with_empty(self) -> None:
        """``None`` for either input is equivalent to an empty value."""
        empty_hash = compute_migration_hash([], "")
        none_hash = compute_migration_hash(None, None)
        assert none_hash == empty_hash

    def test_same_inputs_same_hash(self) -> None:
        """Two calls with the same inputs produce the same hash."""
        caps = _caps("alpha", "beta", "gamma")
        prompt = "You are a helpful assistant."
        h1 = compute_migration_hash(caps, prompt)
        h2 = compute_migration_hash(caps, prompt)
        assert h1 == h2

    def test_capability_order_does_not_matter(self) -> None:
        """Sorting is stable: shuffled capabilities give the same hash."""
        caps_a = _caps("alpha", "beta", "gamma")
        caps_b = _caps("gamma", "alpha", "beta")
        assert compute_migration_hash(caps_a, "") == compute_migration_hash(caps_b, "")

    def test_different_capabilities_different_hash(self) -> None:
        """Adding or removing a capability changes the hash."""
        h1 = compute_migration_hash(_caps("alpha"), "")
        h2 = compute_migration_hash(_caps("alpha", "beta"), "")
        assert h1 != h2

    def test_different_prompt_different_hash(self) -> None:
        """Changing the prompt snapshot changes the hash."""
        caps = _caps("alpha")
        h1 = compute_migration_hash(caps, "prompt A")
        h2 = compute_migration_hash(caps, "prompt B")
        assert h1 != h2

    def test_prompt_vs_capability_collision_resistance(self) -> None:
        """A different prompt alone does not collide with a different capability set.

        Fuzz-guard: ensures the ``:`` delimiter keeps the two halves of
        the payload distinguishable.
        """
        caps_alpha = _caps("alpha")
        caps_beta = _caps("beta")
        # If the formula had no proper separator, the two might collide.
        h_caps = compute_migration_hash(caps_alpha, "X")
        h_prompt = compute_migration_hash(caps_beta, "X")
        assert h_caps != h_prompt

    def test_hash_matches_manual_sha256(self) -> None:
        """The formula is a pure SHA-256 over a documented payload — verify by hand."""
        import json

        caps = _caps("alpha", "beta")
        prompt = "explicit prompt"
        expected_caps_json = json.dumps(
            sorted(caps, key=lambda c: json.dumps(c, sort_keys=True, separators=(",", ":"))),
            separators=(",", ":"),
        )
        expected_prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        expected_payload = f"{expected_caps_json}:{expected_prompt_sha}"
        expected_hash = hashlib.sha256(expected_payload.encode("utf-8")).hexdigest()

        actual = compute_migration_hash(caps, prompt)
        assert actual == expected_hash

    def test_invalid_input_type_raises(self) -> None:
        """Non-iterable inputs raise TypeError (defensive contract)."""
        with pytest.raises(TypeError):
            compute_migration_hash(42, "")  # type: ignore[arg-type]


class TestComputeEmployeeMigrationHash:
    """Wrapper that reads fields off an Employee ORM model."""

    def test_wrapper_uses_employee_fields(self) -> None:
        """The wrapper reads ``capabilities`` and ``prompt_regen_snapshot``."""
        emp = Employee(
            name="test",
            slug="test-emp",
            capabilities=_caps("foo", "bar"),
            prompt_regen_snapshot="hello",
        )
        direct = compute_migration_hash(_caps("foo", "bar"), "hello")
        wrapped = compute_employee_migration_hash(emp)
        assert direct == wrapped

    def test_wrapper_handles_null_capabilities(self) -> None:
        """Legacy rows with ``capabilities=NULL`` hash the same as ``[]``."""
        emp = Employee(
            name="legacy",
            slug="legacy-emp",
            capabilities=None,
            prompt_regen_snapshot=None,
        )
        empty = compute_migration_hash([], None)
        assert compute_employee_migration_hash(emp) == empty
