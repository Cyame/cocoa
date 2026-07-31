"""Unit tests for product-facing avatar display status."""

from app.core.avatar_status import compute_avatar_display_status


def test_running_without_conversation_is_idle() -> None:
    assert compute_avatar_display_status("running", in_conversation=False) == "idle"


def test_running_with_conversation_is_busy() -> None:
    assert compute_avatar_display_status("running", in_conversation=True) == "busy"


def test_pending_is_stopped() -> None:
    assert compute_avatar_display_status("pending") == "stopped"


def test_lifecycle_transients() -> None:
    assert compute_avatar_display_status("creating") == "starting"
    assert compute_avatar_display_status("deploying") == "starting"
    assert compute_avatar_display_status("restarting") == "restarting"
    assert compute_avatar_display_status("deleting") == "deleting"
    assert compute_avatar_display_status("failed") == "start_failed"
