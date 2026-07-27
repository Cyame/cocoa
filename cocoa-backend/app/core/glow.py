"""Derived glow values for topology nodes."""

from dataclasses import dataclass
from enum import Enum
from typing import Final


class GlowIntensity(str, Enum):
    """Discrete visual intensity levels for topology node glows."""

    static = "static"
    weak = "weak"
    low = "low"
    medium = "medium"
    strong = "strong"


@dataclass(frozen=True, slots=True)
class GlowColor:
    """A topology glow color paired with its discrete intensity."""

    color: str
    intensity: GlowIntensity


_DEFAULT_GLOW: Final = GlowColor("#94a3b8", GlowIntensity.weak)
_STATUS_GLOWS: Final[dict[str, GlowColor]] = {
    "running": GlowColor("#10b981", GlowIntensity.strong),
    "idle": GlowColor("#eab308", GlowIntensity.medium),
    "paused": GlowColor("#94a3b8", GlowIntensity.weak),
    "interrupted": GlowColor("#ef4444", GlowIntensity.medium),
    "completed": GlowColor("#3b82f6", GlowIntensity.low),
    "failed": GlowColor("#dc2626", GlowIntensity.strong),
}
_USER_MEMBERSHIP_GLOW: Final = GlowColor("#4f46e5", GlowIntensity.medium)


def loop_status_to_glow(status: str) -> GlowColor:
    """Map a harness loop status to its fixed topology glow."""
    return _STATUS_GLOWS.get(status, _DEFAULT_GLOW)


def user_membership_glow() -> GlowColor:
    """Return the fixed glow for a user membership node."""
    return _USER_MEMBERSHIP_GLOW
