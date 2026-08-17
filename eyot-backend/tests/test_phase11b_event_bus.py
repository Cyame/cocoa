"""P11b: SSE EventBus unit tests."""

import asyncio

import pytest

from app.services.k8s.event_bus import EventBus


@pytest.mark.asyncio
async def test_publish_subscribe_basic() -> None:
    """Publish one event and receive it on a freshly-created subscription."""
    bus = EventBus()
    queue, cleanup = bus.create_subscription("test_chan")

    bus.publish("test_chan", {"foo": "bar"}, event_id="1")

    event = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert event.event == "test_chan"
    assert event.data == {"foo": "bar"}
    assert event.id == "1"

    cleanup()


async def test_subscribe_cleanup() -> None:
    """Cleanup deregisters the queue from the channel registry."""
    bus = EventBus()
    queue, cleanup = bus.create_subscription("chan_a")

    assert bus.subscriber_count("chan_a") == 1
    assert queue in bus._channels["chan_a"]

    cleanup()

    assert bus.subscriber_count("chan_a") == 0
    assert queue not in bus._channels["chan_a"]


def test_publish_to_nonexistent_channel() -> None:
    """Publishing to a channel with no subscribers is a no-op."""
    bus = EventBus()
    # No subscribers registered for "ghost_channel".
    bus.publish("ghost_channel", {"hello": "world"})
    assert bus.subscriber_count("ghost_channel") == 0
