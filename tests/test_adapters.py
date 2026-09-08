import itertools
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from playwright.async_api import TimeoutError as PWTimeout

from foxprice.adapters.demo_static import DemoStaticAdapter, BOOK_TITLE, BOOK_PRICE
from foxprice.adapters.demo_auth import DemoAuthAdapter, PRODUCT_TITLE, PRODUCT_PRICE
from foxprice.core.models import PriceOffer, ErrorResult

pytestmark = pytest.mark.asyncio


def make_context(*page_mocks):
    # Once page_mocks is exhausted, keep returning the last page instead of
    # raising StopIteration — an adapter that ends up calling new_page() an
    # extra time (e.g. after a future implementation change) should fail on
    # its own assertions, not on an unrelated mock plumbing error.
    ctx = AsyncMock()
    ctx.new_page = AsyncMock(
        side_effect=itertools.chain(page_mocks, itertools.repeat(page_mocks[-1]))
    )
    return ctx


def make_card(title: str, price: str, title_selector: str, price_selector: str):
    title_el = MagicMock()
    title_el.inner_text = AsyncMock(return_value=title)

    price_el = MagicMock()
    price_el.inner_text = AsyncMock(return_value=price)

    def _query_selector(selector):
        if selector == title_selector:
            return title_el
        if selector == price_selector:
            return price_el
        return None

    card = MagicMock()
    card.query_selector = AsyncMock(side_effect=_query_selector)
    return card


def make_page(cards=None):
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.query_selector_all = AsyncMock(return_value=cards or [])
    page.close = AsyncMock()
    return page


# --- DemoStaticAdapter tests ---


async def test_demo_static_login_is_noop():
    adapter = DemoStaticAdapter()
    ctx = AsyncMock()
    await adapter.login(ctx)


async def test_demo_static_fetch_returns_offers():
    cards = [
        make_card("Book Title", "£12.99", BOOK_TITLE, BOOK_PRICE) for _ in range(3)
    ]
    page = make_page(cards)
    ctx = make_context(page)

    adapter = DemoStaticAdapter()
    offers, errors = await adapter.fetch_offers(ctx, "PART-001")

    assert len(offers) == 3
    assert errors == []
    assert all(isinstance(o.unit_price, Decimal) for o in offers)
    assert all(o.fuzzy_matched for o in offers)
    assert all(o.supplier == "demo_static" for o in offers)


async def test_demo_static_fetch_timeout_returns_error():
    page = make_page()
    page.goto = AsyncMock(side_effect=PWTimeout("timed out"))
    ctx = make_context(page)

    adapter = DemoStaticAdapter()
    offers, errors = await adapter.fetch_offers(ctx, "P-001")

    assert offers == []
    assert len(errors) == 1
    assert errors[0].error_type == "timeout"


async def test_demo_static_fetch_parse_error_returns_error():
    page = make_page()
    page.wait_for_selector = AsyncMock(side_effect=Exception("selector fail"))
    ctx = make_context(page)

    adapter = DemoStaticAdapter()
    offers, errors = await adapter.fetch_offers(ctx, "P-001")

    assert offers == []
    assert len(errors) == 1
    assert errors[0].error_type == "parse_error"


async def test_demo_static_fetch_empty_cards_returns_not_found():
    page = make_page([])
    ctx = make_context(page)

    adapter = DemoStaticAdapter()
    offers, errors = await adapter.fetch_offers(ctx, "P-001")

    assert offers == []
    assert errors[0].error_type == "not_found"


async def test_demo_static_page_always_closed():
    page = make_page()
    page.goto = AsyncMock(side_effect=PWTimeout("t"))
    page.close = AsyncMock()
    ctx = make_context(page)

    adapter = DemoStaticAdapter()
    await adapter.fetch_offers(ctx, "P-001")

    page.close.assert_called_once()


# --- DemoAuthAdapter tests ---


async def test_demo_auth_login_navigates_and_waits():
    page = make_page()
    ctx = make_context(page)

    adapter = DemoAuthAdapter()
    await adapter.login(ctx)

    page.goto.assert_called_once()
    page.wait_for_selector.assert_called_once()


async def test_demo_auth_is_session_expired_false():
    page = make_page()
    ctx = make_context(page)

    adapter = DemoAuthAdapter()
    result = await adapter.is_session_expired(ctx)

    assert result is False


async def test_demo_auth_is_session_expired_true():
    page = make_page()
    page.wait_for_selector = AsyncMock(side_effect=PWTimeout("t"))
    ctx = make_context(page)

    adapter = DemoAuthAdapter()
    result = await adapter.is_session_expired(ctx)

    assert result is True


async def test_demo_auth_fetch_returns_offers():
    cards = [
        make_card("Product Title", "$29.99", PRODUCT_TITLE, PRODUCT_PRICE)
        for _ in range(3)
    ]
    page = make_page(cards)
    ctx = make_context(page)

    adapter = DemoAuthAdapter()
    offers, errors = await adapter.fetch_offers(ctx, "PART-001")

    assert len(offers) == 3
    assert offers[0].unit_price == Decimal("29.99")


async def test_demo_auth_fetch_timeout():
    page = make_page()
    page.goto = AsyncMock(side_effect=PWTimeout("timed out"))
    ctx = make_context(page)

    adapter = DemoAuthAdapter()
    offers, errors = await adapter.fetch_offers(ctx, "P-001")

    assert errors[0].error_type == "timeout"


async def test_demo_auth_supplier_name():
    assert DemoAuthAdapter.SUPPLIER_NAME == "demo_auth"
    assert DemoStaticAdapter.SUPPLIER_NAME == "demo_static"
