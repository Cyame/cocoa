"""Response schemas for the topology live-status endpoint."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

GlowIntensityLiteral = Literal["static", "weak", "low", "medium", "strong"]


class GlowIntensityOut(BaseModel):
    """Discrete intensity level for a topology node glow."""

    model_config = ConfigDict(extra="forbid")

    intensity: GlowIntensityLiteral


class GlowColorOut(BaseModel):
    """A topology glow color paired with its discrete intensity."""

    model_config = ConfigDict(extra="forbid")

    color: str
    intensity: GlowIntensityLiteral


NodeType = Literal["user", "instance"]


class LiveStatusItemOut(BaseModel):
    """A single topology node's live status for the canvas.

    Per PRD §13.6.7 + phase-15f: instance nodes carry an additional
    ``outdated`` flag (true when ``instance.active_hash !=
    entity.migration_hash``) and the raw ``active_hash`` so the
    portal can render the "needs restart" badge and a hash-comparison
    tooltip.
    """

    model_config = ConfigDict(extra="forbid")

    membership_id: str
    posx: int
    posy: int
    node_type: NodeType
    glow: GlowColorOut
    # Phase-15f T4: instance-membership only. ``user``-type nodes
    # always have ``outdated=False`` and ``active_hash=None``.
    outdated: bool = False
    active_hash: str | None = None
    # Lifecycle of the bound Instance (running/pending/deploying/…).
    # ``null`` for user nodes. Portal uses this to gate @ / Composer chat.
    instance_status: str | None = None
    mentionable: bool = False
    # Product-facing avatar status (busy/idle/stopped/…); preferred for badges.
    display_status: str | None = None
