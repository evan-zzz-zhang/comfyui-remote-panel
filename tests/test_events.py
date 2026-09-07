from __future__ import annotations

import asyncio

import pytest

from comfyui_remote_panel.events import EventBus


@pytest.mark.asyncio
async def test_open_subscription_receives_events_after_snapshot_watermark():
    bus = EventBus()
    subscription = bus.open_subscription()
    watermark = bus.sequence
    bus.publish("job", {"id": "new"})

    event = await asyncio.wait_for(subscription.__anext__(), timeout=1)

    assert watermark == 0
    assert event["sequence"] == 1
    assert event["type"] == "job"
    await subscription.aclose()
    assert not bus._subscribers


@pytest.mark.asyncio
async def test_async_generator_subscribe_still_releases_on_close():
    bus = EventBus()
    iterator = bus.subscribe()
    first = iterator.__aiter__()
    pending = asyncio.create_task(first.__anext__())
    await asyncio.sleep(0)
    assert len(bus._subscribers) == 1

    bus.publish("job", {"id": "one"})
    assert (await pending)["data"] == {"id": "one"}
    await first.aclose()

    assert not bus._subscribers
