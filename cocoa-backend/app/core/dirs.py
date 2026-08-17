"""Eyot filesystem path conventions.

Pure functions that define where Eyot stores its runtime artifacts.
All paths are relative (no leading slash) so callers can compose them
with a configurable data root.

**Instance pod layout (pi-native, 2026-07-31):**

The Instance Host sets ``cwd`` / ``COCOA_WORKSPACE_PATH`` to the PVC root
(default ``/data``). Upstream pi reads project config from ``<cwd>/.pi/``.
Sibling directories are Eyot conventions, not a second config root::

    /data/                 # pi cwd
      .pi/                 # upstream pi project config (SYSTEM.md, settings.json, …)
      work/                # hot scratch (non-cwd)
      memory/              # local memory export cache
      shared/              # workspace shared mount

Path-traversal prevention is mandatory: every function raises
``ValueError`` when its argument contains ``..``.
"""

from pathlib import PurePosixPath

# Relative names under the Instance PVC root (pi cwd).
INSTANCE_ROOT_SUBDIRS: tuple[str, ...] = ("work", "memory", ".pi", "shared")


def _validate_no_traversal(value: str) -> None:
    """Reject ``..`` anywhere in *value* (path-traversal guard).

    Raises:
        ValueError: if *value* contains ``..`` as a path component.
    """
    parts = PurePosixPath(value).parts
    if ".." in parts:
        raise ValueError(f"Path traversal rejected: {value!r} contains '..'")


def entity_dir(entity_slug: str) -> str:
    """Relative path to the per-entity *logical* preset directory (control-plane).

    Historical Eyot contract: ``.pi/<entity_slug>/`` for control-plane
    manifests. This is **not** the pi project dir inside a pod — pods use
    ``<cwd>/.pi/`` (see module docstring).

    Args:
        entity_slug: URL-safe entity identifier (e.g. ``"analyst"``).

    Returns:
        Relative path ending with ``/``.
    """
    _validate_no_traversal(entity_slug)
    return f".pi/{entity_slug}/"


def instance_data_subdir(name: str) -> str:
    """Relative subdir under the Instance PVC / pi cwd (``work``, ``memory``, …)."""
    _validate_no_traversal(name)
    if name not in INSTANCE_ROOT_SUBDIRS:
        raise ValueError(f"Unknown instance data subdir: {name!r}")
    return f"{name}/"


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


def shared_host_path(workspace_id: str, root: str = "/var/cocoa/workspaces") -> str:
    """Absolute hostPath for workspace shared volume (orbstack single-node).

    Production should replace this with an RWX PVC / NFS share.

    ``root`` is the Host mount tree root (defaults to the K8s hostPath); the
    backend threads ``settings.FORNIX_ROOT`` here so the test suite can point
    it at a tmp dir. Pure function — no settings import.
    """
    _validate_no_traversal(workspace_id)
    return f"{root.rstrip('/')}/{workspace_id}/shared"
