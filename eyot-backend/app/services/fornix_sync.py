"""Fornix dual-write sync helper (v4.5, H3 mount-mirror semantics).

DB ``FornixFile`` is the Portal/API truth source; the Host
``<FORNIX_ROOT>/<workspace_id>/shared/`` tree is a *mount mirror* that
instance pods read through their hostPath. Every API write path is a
dual-write: update the DB and mirror the file onto disk.

This module only performs disk operations and raises on failure. It never
touches the DB or the event bus — the API layer owns the session, so on an
exception it must roll back the DB change, emit ``fornix.sync_failed``, and
surface a 5xx (never a silent DB-only or file-only write).
"""

from __future__ import annotations

import os
import shutil

from app.core.config import settings
from app.core.dirs import _validate_no_traversal, shared_host_path


def mirror_root(workspace_id: str) -> str:
    """Absolute shared-mount root for a workspace."""
    return shared_host_path(workspace_id, root=settings.FORNIX_ROOT)


def mirror_abs_path(workspace_id: str, parent_path: str | None, name: str) -> str:
    """Absolute mirror path of a FornixFile; rejects ``..`` traversal."""
    _validate_no_traversal(workspace_id)
    if parent_path is not None:
        _validate_no_traversal(parent_path)
    _validate_no_traversal(name)
    rel = name if not parent_path else f"{parent_path.strip('/')}/{name}"
    return os.path.join(mirror_root(workspace_id), rel)


def sync_write(
    workspace_id: str,
    parent_path: str | None,
    name: str,
    *,
    content: str | None,
    is_directory: bool,
) -> None:
    """Mirror a create: mkdir -p parents; directories -> mkdir, files -> write."""
    target = mirror_abs_path(workspace_id, parent_path, name)
    if is_directory:
        os.makedirs(target, exist_ok=True)
        return
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        fh.write(content or "")


def sync_move(
    workspace_id: str,
    src_parent_path: str | None,
    src_name: str,
    dst_parent_path: str | None,
    dst_name: str,
) -> None:
    """Mirror a rename/move on disk; parents of the destination are created."""
    src = mirror_abs_path(workspace_id, src_parent_path, src_name)
    dst = mirror_abs_path(workspace_id, dst_parent_path, dst_name)
    if os.path.isdir(src) and os.path.exists(dst) and not os.path.isdir(dst):
        raise OSError(f"move target exists and is not a directory: {dst}")
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    shutil.move(src, dst)


def sync_remove(
    workspace_id: str,
    parent_path: str | None,
    name: str,
) -> None:
    """Mirror a delete/archive: remove the file (or directory tree) from disk.

    A missing target is a no-op (the mirror already matches the DB truth);
    real I/O errors (permissions, etc.) propagate to the caller.
    """
    target = mirror_abs_path(workspace_id, parent_path, name)
    if not os.path.exists(target):
        return
    if os.path.isdir(target):
        shutil.rmtree(target)
    else:
        os.remove(target)
