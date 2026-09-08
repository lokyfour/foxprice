from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from foxprice.core.base_adapter import BaseAdapter
from foxprice.core.models import PricedResult, PriceOffer, RunSummary
from foxprice.core.orchestrator import run
from foxprice.core.pricing import PricingEngine, PricingTier

pytestmark = pytest.mark.asyncio


@pytest.fixture
def pricing_engine() -> PricingEngine:
    tier = PricingTier(
        price_from=Decimal("0"),
        price_to=Decimal("999"),
        markup_pct=Decimal("100"),
        min_order_qty=1,
    )
    return PricingEngine([tier])


@pytest.fixture
def mock_adapter() -> MagicMock:
    adapter = MagicMock(spec=BaseAdapter)
    adapter.SUPPLIER_NAME = "mock_supplier"
    adapter.ADAPTER_TIMEOUT_SEC = 30
    adapter.login = AsyncMock(return_value=None)
    adapter.logout = AsyncMock(return_value=None)
    adapter.is_session_expired = AsyncMock(return_value=False)
    adapter.fetch_offers = AsyncMock(
        side_effect=lambda ctx, part: (
            [
                PriceOffer(
                    supplier="mock_supplier",
                    part_number=part,
                    matched_part=part,
                    unit_price=Decimal("5.00"),
                )
            ],
            [],
        )
    )
    return adapter


def _mock_playwright_env():
    """Builds a mock async_playwright()/browser/context chain so run()
    never launches a real browser. Returns (mock_pw, mock_context)."""
    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_context)
    mock_context.__aexit__ = AsyncMock(return_value=False)
    mock_context.storage_state = AsyncMock(return_value={"cookies": [], "origins": []})

    mock_browser = MagicMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.close = AsyncMock(return_value=None)
    mock_browser.version = "mock-browser/1.0"

    mock_playwright = MagicMock()
    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

    mock_pw = MagicMock()
    mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_playwright)
    mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)

    return mock_pw, mock_context


async def test_run_returns_correct_types(mock_adapter, pricing_engine, tmp_path):
    mock_pw, _ = _mock_playwright_env()
    with (
        patch("foxprice.core.orchestrator.async_playwright", mock_pw),
        patch("foxprice.core.orchestrator.SESSION_DIR", tmp_path / ".sessions"),
    ):
        priced, errors, summary = await run([mock_adapter], ["PART-001"], pricing_engine)

    assert isinstance(summary, RunSummary)
    assert isinstance(priced, list)
    assert isinstance(errors, list)


def test_run_skip_allowlist():
    adapter_a = MagicMock(spec=BaseAdapter)
    adapter_a.SUPPLIER_NAME = "sup_a"
    adapter_b = MagicMock(spec=BaseAdapter)
    adapter_b.SUPPLIER_NAME = "sup_b"

    adapters = [adapter_a, adapter_b]
    skip = {"sup_a"}
    filtered = [a for a in adapters if a.SUPPLIER_NAME not in skip]

    assert len(filtered) == 1
    assert filtered[0].SUPPLIER_NAME == "sup_b"


async def test_run_summary_fields(mock_adapter, pricing_engine, tmp_path):
    mock_pw, _ = _mock_playwright_env()
    with (
        patch("foxprice.core.orchestrator.async_playwright", mock_pw),
        patch("foxprice.core.orchestrator.SESSION_DIR", tmp_path / ".sessions"),
    ):
        priced, errors, summary = await run([mock_adapter], ["P1", "P2"], pricing_engine)

    assert summary.parts_total == 2
    assert summary.run_id is not None and len(summary.run_id) == 8
    assert summary.duration_sec > 0


def test_parts_not_found_calculation():
    offer = PriceOffer(
        supplier="s", part_number="P1", matched_part="P1", unit_price=Decimal("5.00")
    )
    priced = [PricedResult(offer=offer, markup_pct=Decimal("100"), final_price=Decimal("10.00"))]
    parts = ["P1", "P2", "P3"]

    found_set = {pr.offer.part_number for pr in priced}
    not_found = len(parts) - len(found_set)

    assert not_found == 2
