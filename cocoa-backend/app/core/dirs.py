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


def entity_dir(entity_slug: str) -> str:
    """Relative path to the per-entity preset directory.

    ``.pi/<entity_slug>/`` holds per-entity manifests and configs
    that are assembled at bootstrap time.

    Args:
        entity_slug: URL-safe entity identifier (e.g. ``"analyst"``).

    Returns:
        Relative path ending with ``/``.
    """
    _validate_no_traversal(entity_slug)
    return f".pi/{entity_slug}/"


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


def fornix_dir(workspace_id: str) -> str:
    """Relative path to the per-workspace 穹窿 (fornix) shared work directory.

    The 穹窿 is the file-share brain area inside the per-workspace CentralHub.
    ``fornix/<workspace_id>/`` is the shared read/write space for all
    entities in the same workspace.

    Args:
        workspace_id: Unique workspace identifier (UUID).

    Returns:
        Relative path ending with ``/``.
    """
    _validate_no_traversal(workspace_id)
    return f"fornix/{workspace_id}/"


def vault_dir(workspace_id: str) -> str:
    """Relative path to the per-workspace cold-archive directory.

    ``vault/<workspace_id>/`` is the long-term archive space — write
    semantics are append-only once a run concludes.

    Args:
        workspace_id: Unique workspace identifier (UUID).

    Returns:
        Relative path ending with ``/``.
    """
    _validate_no_traversal(workspace_id)
    return f"vault/{workspace_id}/"


def memory_export_path(entity_slug: str) -> str:
    """Relative path for the optional /distill JSONL export.

    ``memory/<entity_slug>.jsonl`` is produced by the agent memory
    distillation pipeline when an operator requests an export.
    Memory is DB-backed at runtime; this file is a one-off artifact.

    Args:
        entity_slug: URL-safe entity identifier (e.g. ``"analyst"``).

    Returns:
        Relative file path (no trailing ``/``).
    """
    _validate_no_traversal(entity_slug)
    return f"memory/{entity_slug}.jsonl"
