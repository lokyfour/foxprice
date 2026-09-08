"""Orchestrator drives the full scraping lifecycle.

Uses asyncio.TaskGroup (not gather) for structured concurrency. Work
is distributed via asyncio.Queue (producer/consumer). Each adapter
runs in its own task with asyncio.timeout wrapping the full adapter
run. A watchdog task pings the browser every 60s and logs a warning
if it becomes unresponsive.
"""

import asyncio
import time
import uuid
from asyncio import TaskGroup

from loguru import logger
from playwright.async_api import Browser, async_playwright

from foxprice.core.base_adapter import BaseAdapter
from foxprice.core.models import ErrorResult, PricedResult, RunSummary
from foxprice.core.pricing import PricingEngine
from foxprice.core.retry import CircuitBreakerError, get_breaker, with_retry
from foxprice.core.session import SESSION_DIR, SessionManager


async def _run_adapter(
    browser: Browser,
    adapter: BaseAdapter,
    part_queue: "asyncio.Queue[str | None]",
    result_queue: "asyncio.Queue",
    session_mgr: SessionManager,
    engine: PricingEngine,
) -> None:
    session_path = SESSION_DIR / f"{adapter.SUPPLIER_NAME}.json"
    if session_path.exists():
        ctx = await browser.new_context(storage_state=str(session_path))
    else:
        ctx = await browser.new_context()

    async with ctx:
        await adapter.login(ctx)
        await session_mgr.save(adapter, ctx)
        breaker = get_breaker(adapter.SUPPLIER_NAME)

        while True:
            try:
                part = part_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            assert part is not None

            offers: list = []
            errors: list[ErrorResult] = []
            try:
                offers, errors = await breaker.call_async(
                    with_retry, adapter.fetch_offers, ctx, part
                )
                if await adapter.is_session_expired(ctx):
                    await session_mgr.invalidate(adapter)
                    await adapter.login(ctx)
                    await session_mgr.save(adapter, ctx)
                    offers, errors = await breaker.call_async(
                        with_retry, adapter.fetch_offers, ctx, part
                    )
            except CircuitBreakerError as e:
                offers = []
                errors = [
                    ErrorResult(
                        supplier=adapter.SUPPLIER_NAME,
                        part_number=part,
                        error_type="circuit_open",
                        description=str(e),
                    )
                ]
            except Exception as e:
                offers = []
                errors = [
                    ErrorResult(
                        supplier=adapter.SUPPLIER_NAME,
                        part_number=part,
                        error_type="parse_error",
                        description=str(e),
                    )
                ]

            for offer in offers:
                calc = engine.calculate(offer.unit_price)
                if calc is not None:
                    markup_pct, final_price = calc
                    await result_queue.put(
                        PricedResult(
                            offer=offer,
                            markup_pct=markup_pct,
                            final_price=final_price,
                        )
                    )

            for err in errors:
                await result_queue.put(err)

            part_queue.task_done()

        await adapter.logout(ctx)


async def _watchdog(browser: Browser, interval: int = 60) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            browser.version
        except Exception as e:
            logger.warning(f"watchdog: browser unresponsive: {e}")


async def run(
    adapters: list[BaseAdapter],
    parts: list[str],
    engine: PricingEngine,
    parallel: bool = False,
) -> tuple[list[PricedResult], list[ErrorResult], RunSummary]:
    run_id = str(uuid.uuid4())[:8]
    start = time.monotonic()

    part_queue: "asyncio.Queue[str | None]" = asyncio.Queue()
    for part in parts:
        part_queue.put_nowait(part)

    result_queue: asyncio.Queue = asyncio.Queue()
    session_mgr = SessionManager()

    async def _run_bounded(adapter: BaseAdapter) -> None:
        async with asyncio.timeout(adapter.ADAPTER_TIMEOUT_SEC):
            await _run_adapter(browser, adapter, part_queue, result_queue, session_mgr, engine)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        watchdog_task = asyncio.create_task(_watchdog(browser))
        try:
            if parallel:
                async with TaskGroup() as tg:
                    for adapter in adapters:
                        tg.create_task(_run_bounded(adapter))
            else:
                for adapter in adapters:
                    await _run_bounded(adapter)
        finally:
            watchdog_task.cancel()

        await browser.close()

    priced: list[PricedResult] = []
    errors: list[ErrorResult] = []
    while not result_queue.empty():
        item = result_queue.get_nowait()
        if isinstance(item, PricedResult):
            priced.append(item)
        else:
            errors.append(item)

    parts_found_set = {pr.offer.part_number for pr in priced}
    parts_found = len(parts_found_set)
    parts_not_found = max(len(parts) - parts_found, 0)

    summary = RunSummary(
        run_id=run_id,
        parts_total=len(parts),
        parts_found=parts_found,
        parts_not_found=parts_not_found,
        errors=len(errors),
        duration_sec=time.monotonic() - start,
        suppliers=[a.SUPPLIER_NAME for a in adapters],
        mer_score={a.SUPPLIER_NAME: 0 for a in adapters},
    )
    return priced, errors, summary
