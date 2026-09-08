import pytest

from foxprice.web.sse import SseBus, _buses, create_bus, get_bus, remove_bus

pytestmark = pytest.mark.asyncio


@pytest.fixture
def bus() -> SseBus:
    b = SseBus("test_run_001")
    yield b
    b.close()


@pytest.fixture
def clean_registry():
    _buses.clear()
    yield
    _buses.clear()


async def test_subscribe_returns_queue(bus):
    queue = await bus.subscribe()
    assert queue is not None
    assert queue.maxsize == 200


async def test_publish_delivers_to_subscriber(bus):
    queue = await bus.subscribe()
    await bus.publish("hello")
    item = queue.get_nowait()
    assert item == "data: hello\n\n"


async def test_publish_to_multiple_subscribers(bus):
    q1 = await bus.subscribe()
    q2 = await bus.subscribe()
    await bus.publish("msg")
    assert q1.get_nowait() == "data: msg\n\n"
    assert q2.get_nowait() == "data: msg\n\n"


async def test_publish_after_close_is_noop(bus):
    queue = await bus.subscribe()
    bus.close()
    await bus.publish("after_close")
    item = queue.get_nowait()
    assert item is None
    assert queue.empty()


async def test_close_sends_sentinel(bus):
    queue = await bus.subscribe()
    bus.close()
    item = queue.get_nowait()
    assert item is None


async def test_close_clears_subscribers(bus):
    await bus.subscribe()
    await bus.subscribe()
    bus.close()
    assert bus._subscribers == []


async def test_publish_full_queue_no_crash(bus):
    queue = await bus.subscribe()
    for i in range(200):
        queue.put_nowait(f"item{i}")
    await bus.publish("overflow")


async def test_create_bus_registers_in_registry(clean_registry):
    bus = create_bus("run_abc")
    assert get_bus("run_abc") is bus


async def test_get_bus_missing_returns_none(clean_registry):
    assert get_bus("nonexistent") is None


async def test_remove_bus_closes_and_removes(clean_registry):
    bus = create_bus("run_xyz")
    queue = await bus.subscribe()
    remove_bus("run_xyz")
    assert get_bus("run_xyz") is None
    assert bus._closed is True
    assert queue.get_nowait() is None


async def test_remove_bus_missing_no_crash(clean_registry):
    remove_bus("never_existed")
