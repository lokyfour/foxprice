# Foxprice Architecture

This document describes the internal design of Foxprice for contributors and
anyone building adapters or extending the framework.

---

## Contents

- [Overview](#overview)
- [Directory layout](#directory-layout)
- [Request lifecycle](#request-lifecycle)
- [Core components](#core-components)
  - [Orchestrator](#orchestrator)
  - [Base adapter](#base-adapter)
  - [Session manager](#session-manager)
  - [Retry and circuit breaker](#retry-and-circuit-breaker)
  - [Pricing engine](#pricing-engine)
  - [Reporter](#reporter)
- [Web panel](#web-panel)
- [Data models](#data-models)
- [Design decisions](#design-decisions)
- [Known limitations](#known-limitations)

---

## Overview

Foxprice is a framework, not a scraper. It provides the infrastructure
(concurrency, retries, session persistence, pricing, output) and delegates
site-specific logic to **adapters** — thin classes that know how to log in
and extract prices from one portal.

```
parts.txt / parts.csv
        │
        ▼
  ┌─────────────┐
  │ Orchestrator│  asyncio.TaskGroup + asyncio.Queue
  └──────┬──────┘
         │  one task per adapter
    ┌────┴────┐
    │ Adapter │  login() → fetch_offers() per part
    └────┬────┘
         │  PriceOffer / ErrorResult
    ┌────┴──────┐
    │  Pricing  │  tier lookup, Decimal math, ROUND_HALF_UP
    └────┬──────┘
         │  PricedResult
    ┌────┴──────┐
    │  Reporter │  openpyxl → Excel (4 sheets)
    └───────────┘
```

---

## Directory layout

```
foxprice/                   # installable package
│
├── core/
│   ├── base_adapter.py     # Abstract base — the adapter contract
│   ├── orchestrator.py     # Concurrency engine
│   ├── session.py          # storageState persistence and re-auth
│   ├── retry.py            # tenacity policy + aiobreaker circuit breaker
│   ├── pricing.py          # Tier lookup and Decimal calculation
│   ├── reporter.py         # Excel output
│   └── models.py           # Shared dataclasses
│
├── adapters/
│   ├── demo_static.py      # books.toscrape.com — no auth
│   └── demo_auth.py        # webscraper.io — form login + session
│
├── web/
│   ├── app.py              # FastAPI app, JWT auth, all routes
│   ├── db.py               # aiosqlite schema + queries
│   ├── runner.py           # Subprocess launcher + SSE bus
│   ├── sse.py              # Server-Sent Events per run
│   └── templates/          # Jinja2 HTML templates
│
└── settings.py             # pydantic-settings singleton

tests/                      # pytest — mirrors package structure
main.py                     # CLI entry point
pyproject.toml              # single source of truth for deps + tools
```

---

## Request lifecycle

A single part number moving through the system:

```
1.  main.py          load_parts() → ["PART-001", "PART-002", ...]
2.  orchestrator     put all parts into asyncio.Queue
3.  orchestrator     create one asyncio.Task per adapter (TaskGroup)
4.  adapter task     session_mgr.restore() → load storageState if exists
5.  adapter task     adapter.login(context)
6.  adapter task     session_mgr.save() → persist storageState to disk
7.  loop             part = queue.get_nowait()
8.  retry wrapper    breaker.call_async(with_retry, adapter.fetch_offers, ctx, part)
9.  adapter          page.goto() → wait_for_selector() → extract price text
10. adapter          return [PriceOffer(unit_price=Decimal("12.50"), ...)], []
11. pricing          tier = lookup(unit_price) → final = unit_price * (1 + markup)
12. results queue    put (part, [PricedResult(...)], [])
13. reporter         write Excel: Results / Raw Data / Errors / Settings
```

If step 9 times out → `ErrorResult(error_type="timeout")` returned, not raised.
If step 8 opens the circuit → `ErrorResult(error_type="circuit_open")` returned.
If step 5 detects session expiry → re-login, then retry step 8.

---

## Core components

### Orchestrator

**File:** `foxprice/core/orchestrator.py`

The orchestrator owns the browser process and coordinates all adapter tasks.

Key design choices:

| Choice | Rationale |
|---|---|
| `asyncio.TaskGroup` instead of `gather` | Exceptions cancel siblings; `ExceptionGroup` is surfaced, not swallowed |
| `asyncio.Queue` for part distribution | Eliminates shared mutable state; natural backpressure |
| One browser, N contexts | Contexts are cheap; browser launch is expensive |
| Per-adapter `asyncio.timeout()` | A hung adapter does not block the entire run |
| Watchdog task | Detects dead CDP subprocess and restarts browser |

**Sequential mode** (default, `CONTEXT_POOL_SIZE=1`): adapters run one after
another, sharing the part queue. Safe for portals that block concurrent sessions.

**Parallel mode** (`--parallel`): each adapter gets its own copy of the queue
and runs concurrently inside the `TaskGroup`. Use on machines with enough RAM
(one Chromium context ≈ 50–150 MB).

### Base adapter

**File:** `foxprice/core/base_adapter.py`

Every adapter must implement two methods:

```python
async def login(self, context: BrowserContext) -> None: ...
async def fetch_offers(self, context: BrowserContext, part_number: str
                       ) -> tuple[list[PriceOffer], list[ErrorResult]]: ...
```

Optional override:

```python
async def is_session_expired(self, context: BrowserContext) -> bool: ...
async def logout(self, context: BrowserContext) -> None: ...
```

**Rules for adapter authors:**

- `fetch_offers()` must never raise. Catch all exceptions and return
  an `ErrorResult` instead.
- `unit_price` must be `Decimal` constructed from a string, never from `float`.
- Retry logic lives in the orchestrator, not the adapter. Do not add
  retry loops inside `fetch_offers()`.
- Set `ADAPTER_TIMEOUT_SEC` to a realistic ceiling for your portal.
  Default is 1800 (30 min).

### Session manager

**File:** `foxprice/core/session.py`

Handles Playwright `storageState` — cookies, localStorage, sessionStorage —
so the framework can survive restarts without re-authenticating.

```
.sessions/
└── my_supplier.json    # storageState — gitignored
```

Lifecycle:
1. Before `login()`: `restore()` checks whether a saved state exists.
   If yes, it is passed to `browser.new_context(storage_state=path)`.
2. After `login()`: `save()` writes the current state to disk.
3. After each `fetch_offers()`: orchestrator calls `adapter.is_session_expired()`.
   If expired: `invalidate()` deletes the file, then `login()` runs again.

### Retry and circuit breaker

**File:** `foxprice/core/retry.py`

Two layers of protection against transient failures:

**`with_retry`** (tenacity):
- Retries on `PlaywrightTimeoutError` and `asyncio.TimeoutError`
- Exponential backoff with full jitter (`initial=1s`, `max=30s`)
- Maximum 4 attempts
- Does **not** retry on 400/401/403/404 — those are not transient

**`get_breaker(supplier)`** (aiobreaker):
- One `CircuitBreaker` instance per supplier, stored in `_breakers` dict
- Opens after 5 consecutive failures
- Resets after 60 seconds (half-open probe)
- When open: returns `ErrorResult(error_type="circuit_open")` immediately,
  without touching the browser

Why full jitter? A predictable retry cadence (1s, 2s, 4s...) is fingerprintable
by WAF bot-scoring systems. Jitter randomises the spacing.

### Pricing engine

**File:** `foxprice/core/pricing.py`

Tiers are loaded from `aiosqlite` at run start. The CSV file
(`pricing_tiers.csv`) is only used for the initial import.

Tier boundary semantics: `[price_from, price_to)` — left inclusive, right
exclusive. A price of exactly `5.00` falls into the `5–10` tier, not `0–5`.

Money rules — enforced in CI:
- All prices are `Decimal`, constructed from strings
- No `float` anywhere in the pricing path (`ruff` rule detects float literals
  in `foxprice/core/pricing.py`)
- Final price: `unit_price * (1 + markup_pct / 100)`
- Rounding: `.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)`

### Reporter

**File:** `foxprice/core/reporter.py`

Produces a single `.xlsx` file with four sheets:

| Sheet | Contents |
|---|---|
| Results | Best offer per supplier/warehouse, with final price |
| Raw Data | Every `PricedResult` unfiltered |
| Errors | `ErrorResult` list with type, description, attempt number |
| Settings | Run ID, timestamp, supplier list, tier table, Foxprice version |

---

## Web panel

**Files:** `foxprice/web/`

An optional FastAPI control panel for operators who prefer a UI over the CLI.

```
Browser
  │  HTTP / SSE
  ▼
FastAPI (app.py)
  │
  ├── JWT auth (HttpOnly cookie, 15 min TTL)
  ├── /runs        → launch subprocess, stream logs via SSE
  ├── /tiers       → CRUD on pricing_tiers table
  └── /users       → user management

aiosqlite (db.py)
  └── tables: users, runs, tiers, parts

runner.py
  └── subprocess.Popen(["python", "main.py", ...])
      no shell=True, allowlist-validated args

sse.py
  └── SseBus per run_id
      → asyncio.Queue → text/event-stream
```

Security properties:
- JWT stored in `HttpOnly + Secure + SameSite=lax` cookie
- Login rate-limited (slowapi: 5 req/min)
- Subprocess args validated against `ALLOWED_SUPPLIERS` allowlist
- Web panel is not designed for public internet exposure

---

## Data models

**File:** `foxprice/core/models.py`

```python
PriceOffer       # raw output from adapter: supplier, part, unit_price (Decimal)
PricedResult     # after pricing engine: offer + markup_pct + final_price
ErrorResult      # when something goes wrong: error_type (Literal), description, attempt
RunSummary       # aggregate stats: parts found/not found, errors, MER score per adapter
```

`ErrorType` is a `Literal` — typos are caught by mypy at development time,
not at runtime:

```python
ErrorType = Literal[
    "not_found", "timeout", "auth_error",
    "parse_error", "rfq", "circuit_open", "session_expired"
]
```

**MER score** (Manual Effort Required) — reliability metric per adapter:

| Score | Attempts per part | Meaning |
|---|---|---|
| Low (🟢) | 0–1 | Stable |
| Medium (🟡) | 2–4 | Occasionally retries |
| High (🔴) | 5+ | Unstable — investigate |

---

## Design decisions

**Why not Scrapy?**
Scrapy is built on Twisted (callbacks). `asyncio.TaskGroup` and native async/await
are simpler to reason about for adapter authors who are not framework experts.
Foxprice intentionally keeps the adapter interface minimal: two methods, no
spider/pipeline/middleware concepts to learn.

**Why one browser, not one browser per adapter?**
Browser startup is expensive (~1–2 seconds, ~50 MB RAM). Sharing one browser
with isolated contexts per adapter is the standard pattern in production
Playwright automation. Each context has its own cookies, localStorage, and
network state — full isolation without the cost of a separate process.

**Why `asyncio.Queue` instead of shared list + Lock?**
A queue is a coordination primitive, not a synchronisation primitive. It
eliminates the need for `asyncio.Lock` on the work list entirely, removes whole
classes of race conditions, and provides natural backpressure when the pool is
saturated.

**Why `Decimal` from strings and not integers?**
Integer minor units (cents) are the most robust representation for storage,
but they require a unit convention at every boundary. For a framework that
deals with prices from scraped text (`"$12.50"`, `"€ 1.234,56"`), parsing
directly into `Decimal` from the cleaned string is safer: the conversion is
explicit, the precision is preserved, and `quantize()` applies the final
rounding policy in one place.

---

## Known limitations

| Limitation | Workaround / Roadmap |
|---|---|
| `aiobreaker._breakers` is in-process only | Use `aiobreaker` with `CircuitBreakerStorage` backed by Redis for multi-worker setups (v2.x roadmap) |
| `SseBus` is single event-loop | The web panel must run as a single-process uvicorn instance (`--workers 1`) |
| No proxy rotation built in | Set `PLAYWRIGHT_PROXY` in `.env`; rotation logic belongs in the adapter |
| Windows not tested | CI runs on `ubuntu-latest`; Windows support is best-effort |
| Session files are plaintext JSON | For production use with sensitive credentials, encrypt `.sessions/` at rest |
