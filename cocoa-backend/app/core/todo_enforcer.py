"""Boulder snapshot todo-completion enforcer.

Validates the structure of a Boulder-state todo snapshot before it is
captured into the supervisor or accepted by the snapshot endpoint.
Four invariants are enforced:

1. ``snapshot["todos"]`` is a list (not a tuple, not ``None``).
2. Every todo's ``status`` is one of
   ``{"pending", "in_progress", "completed", "cancelled"}``.
3. Every todo with ``status == "completed"`` carries a non-empty
   ``completion_note`` string — the agent must explain *what* it finished.
4. At most one todo has ``status == "in_progress"`` at any time —
   concurrent execution is not allowed by the boulder state machine.

This module is the single chokepoint: callers (Todo 3 Supervisor and
Todo 6 ``POST /instances/{id}/snapshot``) catch :class:`TodoEnforcerError`
and translate it into HTTP 422 with the error envelope from
``app.core.errors``.
"""

from __future__ import annotations

VALID_STATUSES: set[str] = {"pending", "in_progress", "completed", "cancelled"}


class TodoEnforcerError(ValueError):
    """Raised when a Boulder snapshot violates the todo-completion contract.

    Inherits from :class:`ValueError` so callers may catch either type —
    a snapshot that fails structural validation is, semantically, a
    bad-value failure rather than a runtime error.
    """


def validate_boulder_snapshot(snapshot: dict) -> None:
    """Validate a Boulder todo snapshot in-place.

    Args:
        snapshot: A mapping expected to carry a ``"todos"`` key whose value
            is a list of todo dicts. Each todo dict must have at minimum
            a ``"status"`` key; completed todos must additionally carry a
            non-empty ``"completion_note"`` string.

    Returns:
        ``None`` on success.

    Raises:
        TodoEnforcerError: if any of the four invariants is violated.
            The message includes the failing todo index (for per-item
            checks) or the offending status value, so callers can
            produce actionable error messages.
    """
    todos = snapshot.get("todos")
    if not isinstance(todos, list):
        raise TodoEnforcerError("todos must be a list")

    in_progress_count = 0
    for i, todo in enumerate(todos):
        status = todo.get("status")
        if not isinstance(status, str) or status not in VALID_STATUSES:
            raise TodoEnforcerError(f"invalid todo status: {status!r}")

        if status == "completed":
            note = todo.get("completion_note")
            if not isinstance(note, str) or note == "":
                raise TodoEnforcerError(f"completed todo {i} missing completion_note")

        if status == "in_progress":
            in_progress_count += 1

    if in_progress_count > 1:
        raise TodoEnforcerError(f"multiple in_progress todos: {in_progress_count}")
