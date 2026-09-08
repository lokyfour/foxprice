# Summary

<!-- One paragraph. What does this PR do and why?
     Link to related issue: Closes #N -->

## Type of change

- [ ] Bug fix
- [ ] New adapter
- [ ] New feature
- [ ] Refactor / cleanup
- [ ] Documentation
- [ ] CI / tooling

## Checklist

### All PRs
- [ ] `ruff check .` passes
- [ ] `ruff format --check .` passes
- [ ] `mypy foxprice --ignore-missing-imports` passes
- [ ] `pytest tests/` passes (105/105 or better)
- [ ] CHANGELOG.md updated under `[Unreleased]`

### New adapter
- [ ] Adapter lives in `foxprice/adapters/<name>.py`
- [ ] `SUPPLIER_NAME` and `ADAPTER_TIMEOUT_SEC` are set
- [ ] `login()` and `fetch_offers()` implemented
- [ ] `is_session_expired()` overridden if the portal needs it
- [ ] All prices constructed as `Decimal` from strings (no `float`)
- [ ] `fetch_offers()` never raises — errors go into `ErrorResult`
- [ ] Adapter registered in `main.py`
- [ ] At least a smoke test added in `tests/test_adapters.py`
- [ ] ADAPTER_GUIDE.md checklist reviewed

### Pricing / money changes
- [ ] No `float` anywhere in the pricing path
- [ ] `Decimal` constructed from strings only
- [ ] Rounding uses `quantize(Decimal("0.01"), ROUND_HALF_UP)`

### Security-relevant changes
- [ ] No `shell=True` in subprocess calls
- [ ] No credentials hardcoded
- [ ] Playwright version pin not lowered below 1.55.1

## Screenshots / output (if applicable)

<!-- Paste Excel snippet, log excerpt, or test output -->
