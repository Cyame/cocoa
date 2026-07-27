"""Unit tests for derived topology glow values."""

import pytest

from app.core.glow import GlowIntensity, loop_status_to_glow, user_membership_glow


@pytest.mark.parametrize(
    ("status", "color", "intensity"),
    [
        ("running", "#10b981", GlowIntensity.strong),
        ("idle", "#eab308", GlowIntensity.medium),
        ("paused", "#94a3b8", GlowIntensity.weak),
        ("interrupted", "#ef4444", GlowIntensity.medium),
        ("completed", "#3b82f6", GlowIntensity.low),
        ("failed", "#dc2626", GlowIntensity.strong),
    ],
)
def test_loop_status_to_glow_maps_known_status(
    status: str,
    color: str,
    intensity: GlowIntensity,
) -> None:
    """Known loop statuses return their fixed color and intensity."""
    result = loop_status_to_glow(status)

    assert result.color == color
    assert result.intensity is intensity


def test_loop_status_to_glow_falls_back_for_unknown_status() -> None:
    """Unknown loop statuses use the neutral weak glow."""
    result = loop_status_to_glow("future-status")

    assert result.color == "#94a3b8"
    assert result.intensity is GlowIntensity.weak


def test_user_membership_glow_is_fixed_blue_medium() -> None:
    """User memberships always use the fixed blue medium glow."""
    result = user_membership_glow()

    assert result.color == "#4f46e5"
    assert result.intensity is GlowIntensity.medium
