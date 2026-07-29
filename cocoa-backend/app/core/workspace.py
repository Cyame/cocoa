"""Workspace path generator for instance isolation.

P7 provides a deterministic workspace path that P8 harness uses as the
working directory when launching an agent process. The path is logical
only — no filesystem directories are created here.
"""


def generate_workspace_path(entity_slug: str, instance_id: str) -> str:
    """Return a workspace path scoped to *entity_slug* and *instance_id*.

    Pattern: ``.pi/workspace/{entity_slug}-{instance_id[:8]}/``

    The trailing slash is intentional — it marks the path as a directory
    for harness consumers that need to ``mkdir -p`` later.
    """
    return f".pi/workspace/{entity_slug}-{instance_id[:8]}/"
