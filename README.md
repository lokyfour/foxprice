# 🦊 Foxprice

> B2B price aggregation framework — plug in an adapter per supplier portal, get a structured Excel report.

[![CI](https://github.com/lokyfour/foxprice/actions/workflows/ci.yml/badge.svg)](https://github.com/lokyfour/foxprice/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Playwright ≥1.55.1](https://img.shields.io/badge/playwright-%E2%89%A51.55.1-green.svg)](https://playwright.dev/python/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-black.svg)](https://github.com/astral-sh/ruff)

Foxprice automates price collection from authenticated B2B supplier portals using async Playwright. You write a thin adapter (≈50 lines) for each portal; the framework handles concurrency, retries, session persistence, circuit breaking, pricing tiers, and Excel output.

Not tied to any specific industry or set of sites.

---

## Contents

- [How it works](#how-it-works)
- [Quick start](#quick-start)
- [Project layout](#project-layout)
- [Writing an adapter](#writing-an-adapter)
- [Pricing tiers](#pricing-tiers)
- [Web panel](#web-panel-optional)
- [Configuration reference](#configuration-reference)
- [Running tests](#running-tests)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## How it works

```
parts.txt / parts.csv
        │
        ▼
  Orchestrator  ──── asyncio.TaskGroup + asyncio.Queue
        │
        ├─► Adapter A  ──► Playwright context ──► Portal A
        ├─► Adapter B  ──► Playwright context ──► Portal B
        └─► Adapter N  ──► Playwright context ──► Portal N
                │
                ▼
        Pricing engine  (tiers from DB, Decimal math, ROUND_HALF_UP)
                │
                ▼
        Excel report  (Results / Raw Data / Errors / Settings)
        + structured log
```

**Key design choices:**

| Concern | Approach |
|---|---|
| Concurrency | `asyncio.TaskGroup` + `asyncio.Queue` — no naked `gather` |
| Retries | `tenacity` — exponential backoff with full jitter, `Retry-After`-aware |
| Circuit breaker | `aiobreaker` per adapter — a failing portal doesn't block the run |
| Session persistence | Playwright `storageState` — login once, reuse across restarts |
| Money math | `Decimal` from strings only — `float` in the pricing path is a CI failure |
| Secrets | `.env` / vault hook — nothing hardcoded |

---

## Quick start

```bash
# 1. Clone and install
git clone https://github.com/lokyfour/foxprice.git
cd foxprice
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium

# 2. Configure
cp .env.example .env
# Edit .env: set OUTPUT_DIR, PARTS_FILE, supplier credentials

# 3. Add your parts list
echo "PART-001" > parts.txt
echo "PART-002" >> parts.txt

# 4. Run
python -m foxprice
# → output/pricer_20260908_120000.xlsx
# → output/pricer_20260908_120000.log
```

### Demo run (no credentials needed)

The repo ships two demo adapters that work without any credentials:

```bash
# Scrapes books.toscrape.com — static HTML, no auth
python -m foxprice --adapter demo_static

# Simulates login + session on webscraper.io test site
python -m foxprice --adapter demo_auth
```

---

## Project layout

```
foxprice/
│
├── core/
│   ├── base_adapter.py     # Abstract base — implement login() + fetch_offers()
│   ├── orchestrator.py     # TaskGroup + Queue + bounded context pool
│   ├── session.py          # storageState persistence, expiry detection, re-auth
│   ├── retry.py            # tenacity policy + aiobreaker circuit breaker
│   ├── pricing.py          # Tier lookup, Decimal math, ROUND_HALF_UP
│   ├── reporter.py         # openpyxl Excel output (4 sheets)
│   └── models.py           # PriceOffer, PricedResult, ErrorResult, RunSummary
│
├── adapters/
│   ├── demo_static.py      # Demo: static HTML (books.toscrape.com)
│   └── demo_auth.py        # Demo: form login + session
│
├── web/                    # Optional FastAPI control panel
│   ├── app.py              # Routes, JWT auth, lifespan
│   ├── db.py               # aiosqlite: users, runs, tiers, parts
│   ├── runner.py           # Subprocess launcher, SSE bus
│   ├── sse.py              # Server-Sent Events per run
│   └── templates/          # Jinja2: dashboard, run detail, tiers, users
│
├── tests/                  # pytest — see Running tests
├── docs/
│   ├── architecture.md     # Detailed internals
│   └── adapter-guide.md    # Step-by-step adapter authoring
│
├── pricing_tiers.csv       # Initial import only — DB is source of truth after first run
├── parts.txt               # Default parts list (one SKU per line)
├── .env.example
└── pyproject.toml
```

---

## Writing an adapter

Generate a scaffold:

```bash
python -m foxprice new-adapter my_supplier
# → adapters/my_supplier.py
```

Minimum implementation — two methods:

```python
from playwright.async_api import BrowserContext
from core.base_adapter import BaseAdapter
from core.models import PriceOffer, ErrorResult
from decimal import Decimal

class MySupplierAdapter(BaseAdapter):
    SUPPLIER_NAME = "my_supplier"
    ADAPTER_TIMEOUT_SEC = 1800  # 30 min hard ceiling for the whole run

    async def login(self, context: BrowserContext) -> None:
        page = await context.new_page()
        try:
            await page.goto("https://example.com/login")
            await page.fill("input[name='email']", "user@example.com")
            await page.fill("input[name='password']", "secret")
            await page.click("button[type='submit']")
            await page.wait_for_selector(".dashboard", timeout=15_000)
        finally:
            await page.close()

    async def fetch_offers(
        self,
        context: BrowserContext,
        part_number: str,
    ) -> tuple[list[PriceOffer], list[ErrorResult]]:
        page = await context.new_page()
        try:
            await page.goto(f"https://example.com/search?q={part_number}", timeout=20_000)
            price_text = await page.inner_text("td.price")
            price = Decimal(price_text.replace("$", "").strip())
            return [PriceOffer(
                supplier=self.SUPPLIER_NAME,
                part_number=part_number,
                matched_part=part_number,
                unit_price=price,
            )], []
        except Exception as exc:
            return [], [ErrorResult(self.SUPPLIER_NAME, part_number, "parse_error", str(exc))]
        finally:
            await page.close()
```

Register in `main.py`:

```python
from adapters.my_supplier import MySupplierAdapter
ADAPTERS = [MySupplierAdapter()]
```

Full guide: [docs/adapter-guide.md](docs/adapter-guide.md)

---

## Pricing tiers

Define markup rules in `pricing_tiers.csv` (imported to DB on first run):

```csv
price_from,price_to,markup_pct,min_order_qty
0,5,300,100
5,10,200,50
10,25,150,25
25,9999,100,1
```

Boundaries are `[price_from, price_to)` — left inclusive, right exclusive.  
All math uses `Decimal`. `float` anywhere in the pricing path is a CI failure.

Tiers are editable live via the web panel without restarting anything.

---

## Web panel (optional)

```bash
uvicorn web.app:app --port 8080
# → http://localhost:8080
# Default credentials: admin / admin  ← change immediately
```

Features: launch runs, live log streaming (SSE), run history, tier editor, user management.

> **Security note:** The web panel is intended for internal/local use. Do not expose it to the public internet without a reverse proxy and additional hardening.

---

## Configuration reference

Key `.env` variables:

| Variable | Default | Description |
|---|---|---|
| `PARTS_FILE` | `parts.txt` | Parts list — `.txt` (one per line) or `.csv` |
| `OUTPUT_DIR` | `output` | Directory for Excel reports and logs |
| `CONTEXT_POOL_SIZE` | `1` | Browser contexts per adapter (1 = sequential) |
| `PLAYWRIGHT_VERSION_MIN` | `1.55.1` | Checked at startup (CVE-2025-59288) |
| `WEB_SECRET_KEY` | — | **Required** for web panel — 32+ chars |
| `WEB_ACCESS_TOKEN_TTL` | `900` | JWT lifetime in seconds |
| `SECRET_BACKEND` | `env` | `env` \| `vault` \| `aws_sm` |
| `LOG_LEVEL` | `INFO` | `DEBUG` \| `INFO` \| `WARNING` |

Full reference: [.env.example](.env.example)

---

## Running tests

```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=core --cov=adapters --cov-fail-under=80

# Single module
pytest tests/test_pricing.py -v
```

Test suite covers: pricing golden-file cases, orchestrator task queue, retry/circuit-breaker states, session save/restore, SSE bus, web panel auth, adapter error paths.

---

## CLI reference

```
python -m foxprice [OPTIONS] [COMMAND]

Options:
  --adapter NAME      Run only this adapter (repeatable)
  --skip NAME         Skip this adapter (repeatable)
  --input FILE        Parts file (overrides PARTS_FILE in .env)
  --parallel          Run adapters concurrently
  --dry-run           Parse and validate config without scraping
  --log-level LEVEL   Override LOG_LEVEL

Commands:
  new-adapter NAME    Scaffold a new adapter file
```

---

## Roadmap

| Version | Planned |
|---|---|
| **v0.1** (current) | Core framework, demo adapters, web panel, full test suite |
| **v0.2** | `--parallel` mode, configurable pool size |
| **v0.3** | SAML/OAuth2 auth patterns, webhook notifications |
| **v0.4** | Docker image for web panel |
| **v1.0** | Stable adapter API, PyPI release |

See [CHANGELOG.md](CHANGELOG.md) for release history.

---

## Contributing

Contributions are welcome — bug fixes, new adapters, documentation improvements.

Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a PR.  
By participating you agree to our [Code of Conduct](CODE_OF_CONDUCT.md).

---

## Security

To report a vulnerability, **do not open a public issue**.  
See [SECURITY.md](SECURITY.md) for the responsible disclosure process.

---

## License

[MIT](LICENSE) © 2026 lokyfour
