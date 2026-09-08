"""Per-run SSE bus. The web panel's /runs/{run_id}/stream endpoint
subscribes to this bus and forwards events to the browser. Each log
line from the orchestrator subprocess is published here. Keepalive
pings (": keepalive\\n\\n") prevent proxy/nginx timeout on long-running
scrapes.

SseBus relies on asyncio's single-threaded execution for its
unlocked _subscribers list — it is not thread-safe and must only be
used from coroutines on the same event loop.
"""

import asyncio

from loguru import logger


class SseBus:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._subscribers: list[asyncio.Queue] = []
        self._closed = False

    async def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers.append(queue)
        return queue

    async def publish(self, data: str) -> None:
        if self._closed:
            return

        formatted = f"data: {data}\n\n"
        for queue in self._subscribers:
            try:
                queue.put_nowait(formatted)
            except asyncio.QueueFull:
                logger.warning(f"{self.run_id}: subscriber queue full, dropping event")

    async def keepalive(self) -> None:
        while not self._closed:
            await asyncio.sleep(15)
            for queue in self._subscribers:
                try:
                    queue.put_nowait(": keepalive\n\n")
                except asyncio.QueueFull:
                    logger.warning(f"{self.run_id}: subscriber queue full, dropping keepalive")

    def close(self) -> None:
        self._closed = True
        for queue in self._subscribers:
            try:
                queue.put_nowait(None)
            except asyncio.QueueFull:
                logger.warning(f"{self.run_id}: subscriber queue full, could not deliver close sentinel")
        self._subscribers.clear()


_buses: dict[str, SseBus] = {}


def create_bus(run_id: str) -> SseBus:
    bus = SseBus(run_id)
    _buses[run_id] = bus
    return bus


def get_bus(run_id: str) -> SseBus | None:
    return _buses.get(run_id)


def remove_bus(run_id: str) -> None:
    bus = _buses.pop(run_id, None)
    if bus:
        bus.close()
