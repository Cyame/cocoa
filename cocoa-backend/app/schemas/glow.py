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
    """A single topology node's live status for the canvas."""

    model_config = ConfigDict(extra="forbid")

    membership_id: str
    posx: int
    posy: int
    node_type: NodeType
    glow: GlowColorOut
