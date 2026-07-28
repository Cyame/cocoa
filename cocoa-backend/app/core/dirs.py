"""Cocoa filesystem path conventions.

Pure functions that define where Cocoa stores its runtime artifacts.
All paths are relative (no leading slash) so callers can compose them
with a configurable data root.

Path-traversal prevention is mandatory: every function raises
``ValueError`` when its argument contains ``..``.
"""

from pathlib import PurePosixPath


def _validate_no_traversal(value: str) -> None:
    """Reject ``..`` anywhere in *value* (path-traversal guard).

    Raises:
        ValueError: if *value* contains ``..`` as a path component.
    """
    parts = PurePosixPath(value).parts
    if ".." in parts:
        raise ValueError(f"Path traversal rejected: {value!r} contains '..'")


def employee_dir(employee_slug: str) -> str:
    """Relative path to the per-employee preset directory.

    ``.pi/<employee_slug>/`` holds per-employee manifests and configs
    that are assembled at bootstrap time.

    Args:
        employee_slug: URL-safe employee identifier (e.g. ``"analyst"``).

    Returns:
        Relative path ending with ``/``.
    """
    _validate_no_traversal(employee_slug)
    return f".pi/{employee_slug}/"


def workspace_dir(instance_id: str) -> str:
    """Relative path to the per-instance workspace directory.

    ``workspace/<instance_id>/`` is the PVC-backed scratch area for a
    single agent instance.

    Args:
        instance_id: Unique instance identifier (UUID).

    Returns:
        Relative path ending with ``/``.
    """
    _validate_no_traversal(instance_id)
    return f"workspace/{instance_id}/"


def fornix_dir(office_id: str) -> str:
    """Relative path to the per-office 穹窿 (fornix) shared work directory.

    The 穹窿 is the file-share brain area inside the per-office CentralHub.
    ``fornix/<office_id>/`` is the shared read/write space for all
    employees in the same office.

    Args:
        office_id: Unique office identifier (UUID).

    Returns:
        Relative path ending with ``/``.
    """
    _validate_no_traversal(office_id)
    return f"fornix/{office_id}/"


def vault_dir(office_id: str) -> str:
    """Relative path to the per-office cold-archive directory.

    ``vault/<office_id>/`` is the long-term archive space — write
    semantics are append-only once a run concludes.

    Args:
        office_id: Unique office identifier (UUID).

    Returns:
        Relative path ending with ``/``.
    """
    _validate_no_traversal(office_id)
    return f"vault/{office_id}/"


def memory_export_path(employee_slug: str) -> str:
    """Relative path for the optional /distill JSONL export.

    ``memory/<employee_slug>.jsonl`` is produced by the agent memory
    distillation pipeline when an operator requests an export.
    Memory is DB-backed at runtime; this file is a one-off artifact.

    Args:
        employee_slug: URL-safe employee identifier (e.g. ``"analyst"``).

    Returns:
        Relative file path (no trailing ``/``).
    """
    _validate_no_traversal(employee_slug)
    return f"memory/{employee_slug}.jsonl"
