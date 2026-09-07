from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any


class EventSubscription:
    def __init__(self, bus: "EventBus"):
        self._bus = bus
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        self._closed = False
        bus._subscribers.add(self._queue)

    def __aiter__(self) -> "EventSubscription":
        return self

    async def __anext__(self) -> dict[str, Any]:
        if self._closed:
            raise StopAsyncIteration
        return await self._queue.get()

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._bus._subscribers.discard(self._queue)


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._sequence = 0

    def publish(self, event_type: str, data: Any) -> None:
        self._sequence += 1
        event = {"type": event_type, "data": data, "sequence": self._sequence}
        for queue in tuple(self._subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(event)

    @property
    def sequence(self) -> int:
        return self._sequence

    def open_subscription(self) -> EventSubscription:
        return EventSubscription(self)

    async def subscribe(self) -> AsyncIterator[dict[str, Any]]:
        subscription = self.open_subscription()
        try:
            while True:
                yield await subscription.__anext__()
        finally:
            await subscription.aclose()
