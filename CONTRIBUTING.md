# Contributing to Foxprice

## Setup

```
pip install -e ".[dev]"
playwright install chromium
```

## Branching

- `main` — stable releases only
- Small fix → PR directly to main
- Large feature → feature branch, PR to main when ready

## Commit style

Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`

Example: `feat: add demo_auth adapter`

## Before submitting a PR

- [ ] `pytest tests/` passes
- [ ] `ruff check .` passes
- [ ] `mypy .` passes (strict)
- [ ] New adapter follows ADAPTER_GUIDE.md checklist
- [ ] CHANGELOG.md updated

## Versioning

Semantic Versioning: MAJOR.MINOR.PATCH

- MAJOR: breaking adapter API change
- MINOR: new feature, backward compatible
- PATCH: bug fix

## Adding an adapter

See [ADAPTER_GUIDE.md](ADAPTER_GUIDE.md).

## Running tests

```
pytest tests/ -v
pytest tests/test_pricing.py -v  # fast, no browser
```
