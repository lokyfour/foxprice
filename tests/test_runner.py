import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

from foxprice.web.runner import launch_run, stop_run, ALLOWED_SUPPLIERS
from foxprice.web.sse import _buses

pytestmark = pytest.mark.asyncio


@pytest.fixture
def clean_state():
    _buses.clear()
    with patch("foxprice.web.runner.ALLOWED_SUPPLIERS", {"sup_a", "sup_b"}):
        yield
    _buses.clear()


async def test_launch_run_rejects_unknown_supplier(clean_state):
    with pytest.raises(ValueError):
        await launch_run("r001", 1, ["sup_a"], skip=["unknown_sup"])


async def test_launch_run_creates_sse_bus(clean_state):
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.wait = AsyncMock()
    mock_proc.stdout = AsyncMock()
    mock_proc.stdout.__aiter__ = lambda self: self
    mock_proc.stdout.__anext__ = AsyncMock(side_effect=StopAsyncIteration)

    with (
        patch("foxprice.web.runner.insert_run", AsyncMock()),
        patch("foxprice.web.runner.update_run", AsyncMock()),
        patch("foxprice.web.runner.asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)),
    ):
        await launch_run("r002", 5, ["sup_a"], skip=[])

    assert "r002" not in _buses


async def test_launch_run_publishes_stdout_lines(clean_state):
    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock()

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.wait = AsyncMock()
    mock_proc.stdout = AsyncMock()
    mock_proc.stdout.__aiter__ = lambda self: self
    mock_proc.stdout.__anext__ = AsyncMock(
        side_effect=[b"INFO scraping\n", b"INFO done\n", StopAsyncIteration]
    )

    with (
        patch("foxprice.web.runner.create_bus", return_value=mock_bus),
        patch("foxprice.web.runner.remove_bus"),
        patch("foxprice.web.runner.insert_run", AsyncMock()),
        patch("foxprice.web.runner.update_run", AsyncMock()),
        patch("foxprice.web.runner.asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)),
    ):
        await launch_run("r003", 2, ["sup_a"], skip=[])

    assert mock_bus.publish.call_count == 2


async def test_stop_run_returns_false_for_missing_run(clean_state):
    result = await stop_run("nonexistent_run")
    assert result is False


async def test_stop_run_returns_true_and_closes_bus(clean_state):
    from foxprice.web.sse import create_bus

    create_bus("r_stop")

    with patch("foxprice.web.runner.update_run", AsyncMock()):
        result = await stop_run("r_stop")

    assert result is True
    assert "r_stop" not in _buses
