"""Retry and circuit breaker policy for Foxprice supplier adapters.

Retry policy: only retry on PWTimeoutError and asyncio.TimeoutError —
transient, network-level failures. Never retry on HTTP 400/401/403/404;
those are definitive responses (bad request, auth failure, not found)
and retrying them wastes time and risks tripping supplier rate limits.
HTTP status retrying, if needed, belongs in each adapter, not here.
Backoff uses full jitter (wait_exponential_jitter) so retry cadence
isn't a fixed, fingerprintable pattern that a supplier's bot detection
could key off of.

Circuit breaker policy: after 5 consecutive failures for a given
supplier, the breaker opens and short-circuits further calls for 60
seconds, then allows a single half-open probe to test recovery before
fully closing again.
"""

import asyncio
from typing import Any, Callable, Coroutine

from aiobreaker import CircuitBreaker, CircuitBreakerError
from loguru import logger
from playwright._impl._errors import TimeoutError as PWTimeoutError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(supplier: str) -> CircuitBreaker:
    if supplier not in _breakers:
        _breakers[supplier] = CircuitBreaker(fail_max=5, reset_timeout=60)
    return _breakers[supplier]


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential_jitter(initial=1, max=30),
    retry=retry_if_exception_type((PWTimeoutError, asyncio.TimeoutError)),
    before_sleep=before_sleep_log(logger, "WARNING"),
    reraise=True,
)
async def with_retry(fn: Callable[..., Coroutine[Any, Any, Any]], *args: Any, **kwargs: Any) -> Any:
    return await fn(*args, **kwargs)


__all__ = ["get_breaker", "with_retry", "CircuitBreakerError"]
