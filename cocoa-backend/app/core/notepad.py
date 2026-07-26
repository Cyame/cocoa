"""Append-only notepad engine for plan-scoped note-taking.

Four canonical notepad kinds — ``learnings``, ``issues``, ``decisions``,
``problems`` — are written into ``<workspace>/.omo/notepads/<plan_slug>/``
as plain Markdown files. The contract is append-only: this module exposes
no edit/delete operations, only ``ensure_notepad_dir``, ``append_to_notepad``,
and ``read_notepad``.

Timestamps are ISO 8601 UTC, so reading a notepad always yields a strictly
chronological append log that supervisors and agents can grep deterministically.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

VALID_NOTEPADS: list[str] = ["learnings", "issues", "decisions", "problems"]


async def ensure_notepad_dir(workspace_path: str, plan_slug: str) -> str:
    """Create the per-plan notepad directory and return its absolute path.

    The directory layout is::

        <workspace_path>/.omo/notepads/<plan_slug>/

    Idempotent: ``os.makedirs(..., exist_ok=True)`` is safe to call on
    every append so callers do not need to track directory state.

    Args:
        workspace_path: Root workspace directory (PVC-backed scratch area).
        plan_slug: Plan identifier used as the per-plan subdirectory name.

    Returns:
        Absolute path of the notepad directory (trailing path-separator-less).
    """
    path = os.path.join(workspace_path, ".omo", "notepads", plan_slug)
    os.makedirs(path, exist_ok=True)
    return path


async def append_to_notepad(
    workspace_path: str,
    plan_slug: str,
    notepad_name: str,
    entry: str,
) -> str:
    """Append a timestamped entry to the named notepad file.

    The line written to disk has the form::

        [<ISO-8601-UTC-timestamp>] <entry>

    e.g. ``[2026-07-26T14:00:00+00:00] finished wiring snapshot endpoint``.

    Args:
        workspace_path: Root workspace directory.
        plan_slug: Plan identifier scoping the notepad.
        notepad_name: One of ``VALID_NOTEPADS``; ``learnings``, ``issues``,
            ``decisions``, ``problems``.
        entry: Free-form note text (single line, caller-controlled).

    Returns:
        Absolute path of the notepad file the entry was written to.

    Raises:
        ValueError: if *notepad_name* is not in ``VALID_NOTEPADS``.
    """
    if notepad_name not in VALID_NOTEPADS:
        raise ValueError(f"invalid notepad name: {notepad_name}")

    dir_path = await ensure_notepad_dir(workspace_path, plan_slug)
    filepath = os.path.join(dir_path, f"{notepad_name}.md")
    with open(filepath, "a", encoding="utf-8") as fp:
        fp.write(f"[{datetime.now(timezone.utc).isoformat()}] {entry}\n")
        fp.flush()
    return filepath


async def read_notepad(
    workspace_path: str,
    plan_slug: str,
    notepad_name: str,
) -> str:
    """Read the full content of a notepad file.

    Returns an empty string if the file does not exist yet (rather than
    raising) so callers can safely read optional / never-written notepads
    without try/except boilerplate.

    Args:
        workspace_path: Root workspace directory.
        plan_slug: Plan identifier scoping the notepad.
        notepad_name: One of ``VALID_NOTEPADS``.

    Returns:
        Full file content (UTF-8), or ``""`` if the file does not exist.

    Raises:
        ValueError: if *notepad_name* is not in ``VALID_NOTEPADS``.
    """
    if notepad_name not in VALID_NOTEPADS:
        raise ValueError(f"invalid notepad name: {notepad_name}")

    filepath = os.path.join(workspace_path, ".omo", "notepads", plan_slug, f"{notepad_name}.md")
    try:
        with open(filepath, "r", encoding="utf-8") as fp:
            return fp.read()
    except FileNotFoundError:
        return ""
