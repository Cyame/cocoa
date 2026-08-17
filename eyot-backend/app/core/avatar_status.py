"""Product-facing avatar (化身) display status.

Orthogonal to:
- ``InstanceStatus`` — infra lifecycle (creating/deploying/running/pending/…)
- ``LoopStatus`` — harness Boulder loop (idle/running/paused/…)

Portal lists and topology glow should prefer this vocabulary, not K8s or
harness enums. ``busy`` means an active Composer/Host conversation turn.
"""

from __future__ import annotations

from typing import Literal

AvatarDisplayStatus = Literal[
    "busy",  # 进行中 — actively chatting via Host/Composer
    "idle",  # 空闲 — reachable / running, not in a conversation
    "stopped",  # 已停止 — operator stop (scaled down / pending)
    "starting",  # 启动中 — creating / deploying
    "restarting",  # 重启中
    "deleting",  # 删除中
    "start_failed",  # 启动失败 — transient; callers should soft-delete
]


def compute_avatar_display_status(
    instance_status: str,
    *,
    in_conversation: bool = False,
) -> AvatarDisplayStatus:
    """Map Instance.status (+ optional live conversation) → display status."""
    status = (instance_status or "").strip().lower()
    if status == "deleting":
        return "deleting"
    if status == "restarting":
        return "restarting"
    if status in {"creating", "deploying"}:
        return "starting"
    if status == "failed":
        return "start_failed"
    if status == "pending":
        return "stopped"
    if status == "running":
        return "busy" if in_conversation else "idle"
    return "idle"
