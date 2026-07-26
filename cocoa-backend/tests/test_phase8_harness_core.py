"""P8 core module tests.

Pure-module tests covering the migration round-trip, notepad engine,
and todo-enforcer (none of these touch the API or runtime). All fixtures
shared with sibling test files (``_clear_handlers`` autouse + the
``loop_state_factory``) live in ``tests/conftest.py``.
"""

from __future__ import annotations

import tempfile

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.notepad import VALID_NOTEPADS, append_to_notepad, read_notepad
from app.core.todo_enforcer import TodoEnforcerError, validate_boulder_snapshot


# Raise the test rate-limit ceiling for every test in this module.
@pytest.fixture(autouse=True)
def _raise_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.middleware.rate_limit.MAX_REQUESTS_PER_WINDOW",
        100_000,
    )


# ---------------------------------------------------------------------------
# Migration round-trip
# ---------------------------------------------------------------------------


async def test_loop_state_migration_roundtrip(session: AsyncSession):
    """instance_loop_states table exists with all 13 custom columns + 4 base."""
    result = await session.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'instance_loop_states'"
        )
    )
    cols = {row[0] for row in result.fetchall()}
    expected = {
        "id",
        "created_at",
        "updated_at",
        "deleted_at",  # BaseModel
        "instance_id",
        "loop_status",
        "current_plan_ref",
        "continuation_count",
        "total_token_estimate",
        "wall_clock_started_at",
        "last_checkpoint_at",
        "boulder_snapshot",
        "notepad_refs",
        "max_continuations",
        "max_wall_clock_seconds",
        "max_token_estimate",
        "idle_timeout_seconds",
    }
    assert expected.issubset(cols), f"Missing columns: {expected - cols}"


# ---------------------------------------------------------------------------
# Notepad append + read
# ---------------------------------------------------------------------------


async def test_append_and_read_notepad():
    workspace = tempfile.mkdtemp(prefix="test-notepad-")
    path = await append_to_notepad(workspace, "test-plan", "learnings", "first entry")
    assert path.endswith("learnings.md")
    content = await read_notepad(workspace, "test-plan", "learnings")
    assert "first entry" in content
    assert "[" in content  # timestamp bracket
    assert VALID_NOTEPADS == ["learnings", "issues", "decisions", "problems"]


# ---------------------------------------------------------------------------
# Notepad rejects invalid names
# ---------------------------------------------------------------------------


async def test_invalid_notepad_name_rejected():
    workspace = tempfile.mkdtemp()
    with pytest.raises(ValueError, match="invalid notepad name"):
        await append_to_notepad(workspace, "p", "diary", "x")
    # Verify no delete/edit API exists (append-only contract)
    import app.core.notepad as n

    assert not hasattr(n, "delete_notepad")
    assert not hasattr(n, "edit_notepad")


# ---------------------------------------------------------------------------
# Todo-enforcer
# ---------------------------------------------------------------------------


def test_validate_boulder_snapshot_accepts_valid():
    validate_boulder_snapshot(
        {
            "todos": [
                {"status": "completed", "title": "a", "completion_note": "done"},
                {"status": "in_progress", "title": "b"},
                {"status": "pending", "title": "c"},
                {"status": "cancelled", "title": "d"},
            ]
        }
    )


def test_completed_todo_without_note_rejected():
    with pytest.raises(TodoEnforcerError, match="completion_note"):
        validate_boulder_snapshot({"todos": [{"status": "completed", "title": "x"}]})
    with pytest.raises(TodoEnforcerError, match="completion_note"):
        validate_boulder_snapshot(
            {"todos": [{"status": "completed", "title": "x", "completion_note": ""}]}
        )


def test_multiple_in_progress_rejected():
    with pytest.raises(TodoEnforcerError, match="in_progress"):
        validate_boulder_snapshot(
            {
                "todos": [
                    {"status": "in_progress", "title": "a"},
                    {"status": "in_progress", "title": "b"},
                ]
            }
        )
