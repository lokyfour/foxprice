import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from aiobreaker import CircuitBreakerError
from playwright._impl._errors import TimeoutError as PWTimeout

from foxprice.core.retry import get_breaker, with_retry

pytestmark = pytest.mark.asyncio

# with_retry uses tenacity's wait_exponential_jitter, which sleeps for real
# time between attempts. We patch tenacity's async sleep so retry tests run
# instantly instead of taking several real seconds per test.
_PATCH_SLEEP = patch("tenacity.nap.sleep", new_callable=AsyncMock)


async def test_with_retry_success():
    mock = AsyncMock(return_value="ok")
    result = await with_retry(mock, "arg")
    assert result == "ok"
    assert mock.call_count == 1


@_PATCH_SLEEP
async def test_with_retry_retries_on_pw_timeout(mock_sleep):
    mock = AsyncMock(side_effect=[PWTimeout("t1"), PWTimeout("t2"), "ok"])
    result = await with_retry(mock)
    assert result == "ok"
    assert mock.call_count == 3


@_PATCH_SLEEP
async def test_with_retry_retries_on_asyncio_timeout(mock_sleep):
    mock = AsyncMock(side_effect=[asyncio.TimeoutError(), asyncio.TimeoutError(), "ok"])
    result = await with_retry(mock)
    assert result == "ok"
    assert mock.call_count == 3


@_PATCH_SLEEP
async def test_with_retry_reraises_after_max_attempts(mock_sleep):
    mock = AsyncMock(side_effect=PWTimeout("always"))
    with pytest.raises(PWTimeout):
        await with_retry(mock)
    assert mock.call_count == 4  # stop_after_attempt=4


async def test_with_retry_does_not_retry_value_error():
    mock = AsyncMock(side_effect=ValueError("bad"))
    with pytest.raises(ValueError):
        await with_retry(mock)
    assert mock.call_count == 1


@patch("foxprice.core.retry._breakers", {})
async def test_get_breaker_returns_same_instance():
    b1 = get_breaker("sup_a")
    b2 = get_breaker("sup_a")
    assert b1 is b2


@patch("foxprice.core.retry._breakers", {})
async def test_get_breaker_different_suppliers():
    assert get_breaker("sup_a") is not get_breaker("sup_b")


@patch("foxprice.core.retry._breakers", {})
async def test_circuit_breaker_opens_after_failures():
    breaker = get_breaker("test_open_supplier")
    with patch.object(breaker, "call_async", AsyncMock(side_effect=CircuitBreakerError("open"))):
        with pytest.raises(CircuitBreakerError):
            await breaker.call_async(AsyncMock())
