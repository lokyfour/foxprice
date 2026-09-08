# Foxprice Adapter Guide

## Overview

An adapter is a small Playwright-driven class, one per supplier, that
knows how to log into that supplier's site (if needed) and look up
prices for a part number. Every adapter subclasses `BaseAdapter`
(`core/base_adapter.py`) and implements its Template Method contract —
`login`, `fetch_offers`, and optionally `logout` and
`is_session_expired`. The orchestrator (`core/orchestrator.py`) drives
every adapter through the same lifecycle (login → fetch_offers loop →
logout) regardless of supplier, using `asyncio.TaskGroup`,
per-supplier circuit breakers, and retry with backoff. Adapters focus
purely on "how do I get a price out of this specific site" — session
persistence, retries, concurrency, and markup calculation all live
outside the adapter.

## Quick start

```
python main.py new-adapter my_supplier
```

This scaffolds `adapters/my_supplier.py` with a `MySupplierAdapter`
class that already subclasses `BaseAdapter`, sets
`SUPPLIER_NAME = "my_supplier"`, and stubs `login` and `fetch_offers`
with `raise NotImplementedError` and a `# TODO` comment. Fill those
in, then register the class in `ADAPTERS` in `main.py`.

## The BaseAdapter contract

### `login(context: BrowserContext) -> None`

Called once per run, before any `fetch_offers` calls, on a fresh
`BrowserContext`. For sites with no real authentication, this can
just navigate to the homepage and confirm it loaded (see
`adapters/demo_auth.py`). For sites with real login, submit
credentials and wait for a selector that only appears when
authenticated. After `login` returns, the orchestrator calls
`context.storage_state()` and persists it via `SessionManager` — you
don't need to save state yourself, just make sure the context is
actually logged in by the time `login` returns.

### `fetch_offers(context: BrowserContext, part_number: str) -> tuple[list[PriceOffer], list[ErrorResult]]`

Looks up one part number and returns `(offers, errors)`. This method
**must never raise** — the orchestrator does not wrap individual
`fetch_offers` calls in a try/except beyond what retry and the circuit
breaker already provide; an uncaught exception here is a bug in the
adapter, not expected control flow. Catch everything internally and
translate failures into `ErrorResult` entries instead. `unit_price` on
every `PriceOffer` must be a `Decimal` constructed from a string (e.g.
`Decimal(price_text)`), never from a `float` — see [Pricing
rules](#pricing-rules).

### `logout(context: BrowserContext) -> None`

Optional. Default is a no-op (`BaseAdapter.logout` does nothing).
Override only if the supplier's site needs an explicit
server-side logout to free a session slot or avoid leaving a stale
session flagged as active.

### `is_session_expired(context: BrowserContext) -> bool`

Optional. Default is `False` (never expired). Override it if the
supplier's session can expire mid-run. The orchestrator calls this
after each `fetch_offers` call; if it returns `True`, the orchestrator
invalidates the saved session, calls `login` again, and retries the
same part once before moving on.

## Class attributes

- `SUPPLIER_NAME` — must be unique across all adapters. It's used as
  the dict key for circuit breakers (`core/retry.py`), the session
  filename (`.sessions/{SUPPLIER_NAME}.json`), and the supplier column
  in reports. Two adapters sharing a name will silently share session
  state and circuit breaker.
- `ADAPTER_TIMEOUT_SEC` — default `1800` (from `BaseAdapter`), wraps
  the adapter's entire run (login + every `fetch_offers` call) in
  `asyncio.timeout`. Tune this down for fast, part-heavy sites and up
  for slow ones — a run that blows through this timeout is cancelled
  mid-flight, so err generous rather than tight.

## Pricing rules

`fetch_offers` returns the **raw** `unit_price` scraped from the
supplier's site. The orchestrator — not the adapter — looks up the
matching `PricingTier` and applies markup via
`PricingEngine.calculate()`. An adapter must never apply markup, round
a price, or otherwise adjust it beyond parsing it off the page.
`unit_price` must be built as `Decimal("12.34")` from a string, never
`Decimal(12.34)` from a float — float construction introduces binary
rounding error that string construction avoids entirely.

## Error handling

`ErrorType` (`core/models.py`) is a fixed set of literals:

| Value              | When to use it                                                   |
|---------------------|-------------------------------------------------------------------|
| `not_found`         | The search completed but no matching product was found.          |
| `timeout`           | A page navigation or selector wait timed out.                    |
| `auth_error`        | Login failed (bad credentials, blocked account, CAPTCHA).        |
| `parse_error`       | The page loaded but the expected markup/selectors weren't there. |
| `rfq`                | The supplier only offers this part on request (no listed price). |
| `circuit_open`      | Reserved for the orchestrator — don't raise this from an adapter.|
| `session_expired`   | Reserved for the orchestrator's own retry-after-expiry logic.    |

`fetch_offers` must catch every exception it can raise internally
(Playwright timeouts, selector misses, `Decimal` parse failures) and
return an `ErrorResult` with the right `error_type` instead of letting
it propagate. See `adapters/demo_static.py` for the standard
try/except shape: catch `PWTimeout` for `timeout`, catch broad
`Exception` for `parse_error`.

## Session management

Foxprice persists Playwright's `storageState` (cookies + localStorage)
per supplier so a login doesn't have to happen on every run:

1. The orchestrator calls `adapter.login(context)` once at the start
   of the adapter's run.
2. It then calls `SessionManager.save(adapter, ctx)`, which writes
   `context.storage_state()` to `.sessions/{SUPPLIER_NAME}.json`.
3. On the next run, if that file exists, the orchestrator passes its
   path as `storage_state=` when creating the new `BrowserContext` —
   Playwright only accepts `storage_state` at context-creation time,
   so this happens before your adapter code ever runs.
4. After each `fetch_offers` call, the orchestrator calls
   `adapter.is_session_expired(context)`.
5. If it returns `True`, the orchestrator calls
   `SessionManager.invalidate(adapter)` (deleting the stale session
   file), calls `login` again, saves the new session, and retries the
   part.

`.sessions/` holds live authentication cookies and must stay in
`.gitignore` — never commit it.

## Testing your adapter

1. Register your adapter instance in the `ADAPTERS` list in
   `main.py`.
2. Add a `parts.txt` with a few known part numbers for the supplier.
3. Run `python main.py --dry-run` (or `python main.py run --dry-run`)
   to sanity-check that your adapter imports and instantiates cleanly.
   Note: this only checks that adapters load and parts parse — it does
   **not** launch a browser or scrape anything.
4. Add a unit test under `tests/` that mocks `BrowserContext` (see
   `tests/test_session.py` and `tests/test_orchestrator.py` for the
   `MagicMock(spec=BaseAdapter)` / `AsyncMock` patterns already used in
   this repo) and exercises `fetch_offers` against a fixed page
   structure, or against a mocked `page.query_selector_all` result if
   you don't want a real browser in CI.

## Real adapter example skeleton

This is the same template `new-adapter` generates:

```python
"""Adapter for my_supplier."""

from playwright.async_api import BrowserContext

from core.base_adapter import BaseAdapter
from core.models import ErrorResult, PriceOffer


class MySupplierAdapter(BaseAdapter):
    SUPPLIER_NAME = "my_supplier"

    async def login(self, context: BrowserContext) -> None:
        # TODO: implement login flow for my_supplier
        raise NotImplementedError

    async def fetch_offers(
        self, context: BrowserContext, part_number: str
    ) -> tuple[list[PriceOffer], list[ErrorResult]]:
        # TODO: implement search + parsing for my_supplier
        raise NotImplementedError
```

## Checklist

Before submitting a new adapter:

- [ ] `SUPPLIER_NAME` is unique
- [ ] `fetch_offers` never raises
- [ ] `unit_price` is `Decimal` from string
- [ ] `login` saves storageState
- [ ] `is_session_expired` implemented if site has sessions
- [ ] `ADAPTER_TIMEOUT_SEC` set realistically
- [ ] Selectors are module-level constants
- [ ] Added to `ADAPTERS` in `main.py`
- [ ] Test added in `tests/`
